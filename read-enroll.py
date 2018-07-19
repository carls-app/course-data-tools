#!/usr/bin/env python3
""" Sonia Moreno, 9/2017
 Scrapes data from Carleton Enroll website containing course schedule information.
 """

from bs4 import BeautifulSoup
from argparse import ArgumentParser
from urllib.parse import parse_qs
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import itertools
import requests
import os
import re
import sys
import time
import json
from pathlib import Path
import hashlib
import datetime


def json_folder_map(folder, name='index', dry_run=False):
    output = {
        'files': [],
        'type': 'courses',
    }

    for file in os.scandir(folder):
        filename = file.name
        if filename.startswith('.'):
            continue

        filepath = folder / filename
        with open(filepath, 'rb') as infile:
            basename, extension = os.path.splitext(filename)
            extension = extension[1:]  # splitext's extension includes the preceding dot
            year = basename[0:2]
            year = '19' + year if year == '99' else '20' + year
            year = int(year)
            semester = basename[2:4]
            if semester == 'FA':
                semester = 1
            elif semester == 'WI':
                semester = 2
            elif semester == 'SP':
                semester = 3

            info = {
                'path': f'terms/{filename}',
                'hash': hashlib.sha256(infile.read()).hexdigest(),
                'year': year,  # eg: 19943.json -> 1994
                'term': int(str(year) + str(semester)),  # eg: 19943.json -> 19943
                'semester': basename[2:4],
                'type': extension,
            }

            output['files'].append(OrderedDict(sorted(info.items())))

    output['files'] = sorted(output['files'], key=lambda item: item['path'])
    output = OrderedDict(sorted(output.items()))

    print('Hashed files')
    if dry_run:
        return

    index_path = folder / '..' / f'{name}.json'
    with open(index_path, 'w') as outfile:
        json.dump(output, outfile, indent='\t', ensure_ascii=False)
        outfile.write('\n')

    print('Wrote', index_path)


def expand_term(term):
    year, sem = term[:2], term[2:]
    year = int(f'20{year}') if year < '90' else int(f'19{year}')
    return year, sem


def discover_terms(*, first, last):
    term_names = ['FA', 'WI', 'SP']

    first_year = first if first else ''
    first_sem = None
    last_year = last if last else ''
    last_sem = None

    if first_year:
        first_year, first_sem = expand_term(first_year)
    if last_year:
        last_year, last_sem = expand_term(last_year)

    first_year = first_year if first_year else datetime.date.today().year - 4
    last_year = last_year if last_year else datetime.date.today().year

    for y in range(first_year, last_year + 1):
        terms = term_names
        year = str(y)[2:]

        if y == first_year and first_sem:
            terms = term_names[term_names.index(first_sem):]
            if first_year == last_year and last_sem:
                terms = term_names[term_names.index(first_sem):term_names.index(last_sem) + 1]
        elif y == last_year and last_sem:
            terms = term_names[:term_names.index(last_sem) + 1]

        for t in terms:
            yield f'{year}{t}'


def fetch_academic_terms():
    """Returns a list of academic terms that user can choose from."""
    html_enroll = requests.get('https://apps.carleton.edu/campus/registrar/schedule/enroll/').text
    soup = BeautifulSoup(html_enroll, 'lxml')
    opts = soup.select_one("#termElement").find_all("option")
    return [opt['value'] for opt in opts]


def fetch_subjects():
    """Returns a list of course subjects."""
    html_enroll = requests.get('https://apps.carleton.edu/campus/registrar/schedule/enroll/').text
    soup = BeautifulSoup(html_enroll, 'lxml')

    subject_summary = soup.select_one("#subjectElement")

    # Create a list with subjects, excluding 'Selected' tag (first item)
    subjects = subject_summary.find_all("option")[1:]

    # Each item is currently in the form: 'Computer Science (CS)'. We only
    # want the abbreviation in the parentheses.
    abbr = re.compile(r'\((.*?)\)')
    return [abbr.search(item.get_text()).group(1) for item in subjects]


def process_course(course, term):
    course_num = course.select_one(".coursenum")

    year, semester = expand_term(term)

    # Split apart the deptnum
    subject, number = course_num.get_text().strip().split(' ')
    number, section = number.split('.')

    course_type = 'Course'
    if number[-1] == 'L':
        course_type = 'Lab'
    elif number[-1] == 'J':
        course_type = 'Juried'
    elif number[-1] == 'F':
        course_type = 'FLAC'
    elif number[-1] == 'S':
        course_type = 'St. Olaf'

    # Finds title attribute within each course
    # Only takes the actual name of the course, which is next to the coursenum attribute
    # but not within its own tag
    title = course.select_one(".title .coursenum").next_sibling.strip()

    # Find the teachers
    if course.select(".faculty"):
        instructors = [' '.join(inst.get_text().strip().split()) for inst in course.select(".faculty a")]
        instructors = [name for name in instructors if name]
    else:
        instructors = []

    # Get the course summary, if possible
    if course.select_one(".faculty") and course.select_one(".faculty").next_sibling:
        summary = str(course.select_one(".faculty").next_sibling).strip()
    elif course.select_one('.prereq') and course.select_one('.prereq').previous_sibling:
        summary = str(course.select_one('.prereq').previous_sibling).strip()
    elif course.select_one('.description'):
        summary = course.select_one('.description').get_text().strip()
    else:
        summary = None
    if not summary:
        summary = None

    # Pull out the prereqs
    if course.select_one('.prereq'):
        prereq = ' '.join(course.select_one('.prereq').get_text().split()).strip() or None
    else:
        prereq = None

    # and the comments
    comments = [el.get_text().strip() for el in course.select('.comments')]

    # Extract the course status
    status = course.select_one('.statusName').get_text().strip().strip(':')
    if not status:
        status = None

    if course.select_one(".statusName").next_sibling:
        status_text = str(course.select_one(".statusName").next_sibling).strip()
        total_size = int(re.search(r'Size: (\d+)', status_text).group(1))
        registered = int(re.search(r'Registered: (\d+)', status_text).group(1))
        waitlist = int(re.search(r'Waitlist: (\d+)', status_text).group(1))
        size = {'total': total_size, 'registered': registered, 'waitlist': waitlist}
    else:
        size = None

    if course.select_one('.codes.gov_codes'):
        tags = [{
            'name': code.get_text().strip(),
            'code': parse_qs(code.get('href')).get('other_code[]', []),
        } for code in course.select('.codes.gov_codes a')]
        tags = [tag['code'][0] if len(tag['code']) else tag['name'] for tag in tags]
    else:
        tags = []

    if course.select_one('.codes.overlays'):
        requirements = [{
            'name': code.get_text().strip(),
            'code': parse_qs(code.get('href')).get('requirements[]', [])
                        or parse_qs(code.get('href')).get('overlays[]', []),
        } for code in course.select('.codes.overlays a')]
        requirements = [req['code'][0] if len(req['code']) else req['name'] for req in requirements]
    else:
        requirements = []

    if course.select_one('.credits'):
        credits_el = course.select_one('.credits')
        credit_count = float(re.search(r'([\d.])+', credits_el.get_text()).group(1))

        if credits_el.select_one('abbr'):
            scnc = credits_el.select_one('abbr').get_text().strip()
            assert scnc == 'S/CR/NC'
            scnc = True if scnc == 'S/CR/NC' else None
        else:
            scnc = None
    else:
        credit_count = None
        scnc = None

    if course.select_one('.textbooks'):
        el = course.select_one('.textbooks')
        synonym = re.search(r'Synonym: (\d+)', el.get_text()).group(1)
    else:
        synonym = None

    if course.select_one('.schedule *'):
        # Start and end times for courses that have set times
        # Account for classes without set times
        schedule = course.select_one('.schedule')

        locations = [a.get_text().strip() for a in course.select('.locations a')]

        # there is at least one course that occurs on Saturday
        days = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
        day_count = len(schedule.select('tr')[0].select('th'))
        if day_count == 7:
            days = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

        times = []
        for tr in schedule.select('tr')[1:]:
            for i, td in enumerate(tr.select('td')):
                if len(td.select('.start')) > 1 or len(td.select('.end')) > 1:
                    raise Exception('multiple times on the same day!')

                start = td.select_one('.start')
                end = td.select_one('.end')

                if (start and not end) or (end and not start):
                    raise Exception('unmatched start/end times!')

                if not start or not end:
                    continue

                day = days[i]
                times.append({
                    'day': day,
                    'start': start.get_text().strip(),
                    'end': end.get_text().strip(),
                })

        offerings = {'times': times, 'locations': locations}
    else:
        offerings = None

    return {
        'id': f'{year}{semester} {subject} {number}.{section}',
        'comments': comments,
        'credits': credit_count,
        'instructors': instructors,
        'number': number,
        'offerings': offerings,
        'prerequisites': prereq,
        'requirements': requirements,
        'scnc': scnc,
        'section': section,
        'semester': semester,
        'size': size,
        'status': status,
        'subject': subject,
        'summary': summary,
        'synonym': synonym,
        'tags': tags,
        'title': title,
        'type': course_type,
        'year': year,
    }


def clean_html(html):
    # Clean up the returned HTML to optimize storage size
    soup = BeautifulSoup(html, 'lxml')

    # only save the enroll data
    soup = soup.select_one('#enrollModule')

    # remove the "my courses" block
    if soup.select_one('#myCourses'):
        soup.select_one('#myCourses').decompose()

    # remove the search form at the bottom
    if soup.select_one('#disco_form'):
        soup.select_one('#disco_form').decompose()

    # remove the "search description" at the top
    # e.g., [Your search for courses for 16/SP and COGSC found 1 course.]
    if soup.select_one('.searchDescription'):
        soup.select_one('.searchDescription').decompose()

    return soup.prettify().strip()


def fetch_subject_for_term(*, term, subject):
    html_string = f'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term={term}&subject={subject}'

    # Course listings for subject during term provided
    html = requests.get(html_string).text

    return clean_html(html)


def extract_courses(*, html, term):
    """ Returns dict object with course number, course name, and start/end times for each course
    Finds course info based on the academic term and subject chosen (in this case, Winter 2018)
    """
    soup = BeautifulSoup(html, 'lxml')

    # Creates list of all items with course as class attribute, excluding related courses
    exact_courses_list = soup.select_one('#enrollModule .courses')
    courses = exact_courses_list.select('.course') if exact_courses_list else []
    for course in courses:
        yield process_course(course, term)


def fetch_and_save(*, term, subject, root, delay):
    folder = root / 'indices' / term / subject
    folder.mkdir(parents=True, exist_ok=True)

    html = fetch_subject_for_term(term=term, subject=subject)
    with open(folder / '_index.html', 'w') as outfile:
        outfile.write(html)
        outfile.write('\n')

    time.sleep(delay)

    return html


def cmd_fetch(*, args, root):
    for term, subject in itertools.product(args.terms, args.subjects):
        ident = f'{term}/{subject}'
        try:
            data = fetch_and_save(term=term,
                           subject=subject,
                           root=root,
                           delay=args.delay)

            print(f'{ident} page is {len(data)} bytes')
        except Exception as e:
            print(f'{ident} generated an exception: {e}')


def clean_and_save(*, path: Path):
    with open(path, 'r') as infile:
        html = infile.read()

    cleaned = clean_html(html)

    with open(path, 'w') as outfile:
        outfile.write(cleaned)
        outfile.write('\n')


def cmd_clean(*, args, root):
    index_dir = root / 'indices'

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for subject_dir in [d for d in index_dir.glob('*/*') if d.is_dir()]:
            path = subject_dir / '_index.html'
            key = executor.submit(clean_and_save, path=path)
            futures[key] = f'{subject_dir.parent.name}/{subject_dir.name}'

        for future in as_completed(futures):
            ident = futures[future]

            # noinspection PyBroadException
            try:
                future.result()
            except Exception as e:
                print(f'{ident} generated an exception: {e}')
            else:
                print(f'completed {ident}')


def extract_and_save(*, html_file: Path, out_dir: Path, term: str):
    with open(html_file, 'r') as infile:
        html = infile.read()

    seen = set()
    for course in extract_courses(html=html, term=term):
        filename = out_dir / f'{course["number"]}.{course["section"]}.json'
        with open(filename, 'w') as outfile:
            json.dump(course, outfile, indent='\t', sort_keys=True, ensure_ascii=False)
            outfile.write('\n')
            seen.add(filename)

    # because we run per term, then per subject, we won't delete things that
    # aren't in the current run, but we will delete things that Carleton
    # doesn't list anymore. so we run the deletion at the end of
    # `extract_and_save`.
    exists = {file for file in out_dir.glob('*.json')}
    to_delete = exists - seen

    for file in to_delete:
        file.unlink()


def cmd_extract(*, args, root):
    index_dir = root / 'indices'
    files_dir = root / 'courses'

    to_process = [d for d in index_dir.glob('*/*') if d.is_dir()]

    if args.debug:
        for subject_dir in to_process:
            html_file = subject_dir / '_index.html'

            term = subject_dir.parent.name
            subject = subject_dir.name
            if term not in args.terms:
                continue

            out_dir = files_dir / term / subject
            out_dir.mkdir(parents=True, exist_ok=True)

            print(f'{subject_dir.parent.name}/{subject_dir.name}')
            extract_and_save(html_file=html_file, out_dir=out_dir, term=term)

        return

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for subject_dir in to_process:
            html_file = subject_dir / '_index.html'

            term = subject_dir.parent.name
            subject = subject_dir.name
            if term not in args.terms:
                continue

            out_dir = files_dir / term / subject
            out_dir.mkdir(parents=True, exist_ok=True)

            key = executor.submit(extract_and_save, html_file=html_file, out_dir=out_dir, term=term)
            futures[key] = f'{subject_dir.parent.name}/{subject_dir.name}'

        for future in as_completed(futures):
            ident = futures[future]

            # noinspection PyBroadException
            try:
                future.result()
            except Exception as e:
                print(f'{ident} generated an exception: {e}')
            else:
                print(f'completed {ident}')


def do_bundle(term, terms_dir):
    subjects = []

    for subject in [d for d in term.glob('*') if d.is_dir()]:
        print(f'bundling term "{term.name}", subject "{subject.name}"', file=sys.stderr)

        courses = []
        for file in subject.glob('*.json'):
            with open(file, 'r') as infile:
                courses.append(json.load(infile))

        subjects.append(courses)

    # terms[term.name] = subjects
    with open(terms_dir / f'{term.name}.json', 'w') as outfile:
        print(f'saving {term.name} bundle')
        all_courses = [courses_set for subject in subjects for courses_set in subject]
        json.dump(all_courses, outfile, indent='\t', sort_keys=True, ensure_ascii=False)
        outfile.write('\n')


def cmd_bundle(*, args, root):
    terms = {}

    terms_dir = root / 'terms'
    terms_dir.mkdir(exist_ok=True)

    files_dir = root / 'courses'

    if args.debug:
        for term in [d for d in files_dir.glob('*') if d.is_dir()]:
            do_bundle(term=term, terms_dir=terms_dir)

        json_folder_map(folder=terms_dir, name='info')

        return

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}

        for term in [d for d in files_dir.glob('*') if d.is_dir()]:
            key = executor.submit(do_bundle, term=term, terms_dir=terms_dir)
            futures[key] = term.name

        for future in as_completed(futures):
            ident = futures[future]

            # noinspection PyBroadException
            try:
                future.result()
            except Exception as e:
                print(f'{ident} generated an exception: {e}')
            else:
                print(f'completed {ident}')

    json_folder_map(folder=terms_dir, name='info')


def main():
    parser = ArgumentParser()
    parser.add_argument('command', action='store',
                        choices=['fetch', 'clean', 'extract', 'bundle'],
                        help='Which command to execute')
    parser.add_argument('terms', action='store', nargs='*', metavar='TERM',
                        help='A term, like 18WI or 15SP')
    parser.add_argument('--dest', action='store',
                        default='../course-data',
                        help='The folder to output data files to')
    parser.add_argument('--subjects', action='store',
                        type=lambda x: x.split(','),
                        help='If given, only fetch these subjects (e.g., WGST,CS')
    parser.add_argument('--print-subjects', action='store_true',
                        help='Print the known subjects, then exit')
    parser.add_argument('--print-terms', action='store_true',
                        help='Print the known terms, then exit')
    parser.add_argument('--delay', action='store',
                        type=float, default=0.5,
                        help='Control the delay between term/subject fetches, in seconds (be nice)')
    parser.add_argument('--debug', action='store_true',
                        help='Enables debugging mode')
    parser.add_argument('--first-term', action='store', metavar='TERM',
                        help='Fetch terms from the given term until --last-term')
    parser.add_argument('--last-term', action='store', metavar='TERM',
                        help='Fetch terms from --first-term until the given term')
    parser.add_argument('-w', '--workers', action='store', metavar='N',
                        type=int, default=0,
                        help='How many worker processes to use (be nice to Enroll)')

    args = parser.parse_args()

    if not args.subjects:
        args.subjects = fetch_subjects()

    if args.print_subjects:
        [print(s) for s in args.subjects]
        return

    if not args.terms:
        if args.first_term or args.last_term:
            args.terms = list(discover_terms(first=args.first_term, last=args.last_term))
        else:
            args.terms = fetch_academic_terms()

    if args.print_terms:
        [print(s) for s in args.terms]
        return

    root = Path(args.dest) if args.dest else Path('..') / 'course-data'

    if args.command == 'fetch':
        if args.workers is 0:
            args.workers = 1
        cmd_fetch(args=args, root=root)
    if args.command == 'clean':
        if args.workers is 0:
            args.workers = cpu_count()
        cmd_clean(args=args, root=root)
    elif args.command == 'extract':
        if args.workers is 0:
            args.workers = cpu_count()
        cmd_extract(args=args, root=root)
    elif args.command == 'bundle':
        if args.workers is 0:
            args.workers = cpu_count()
        cmd_bundle(args=args, root=root)


if __name__ == '__main__':
    main()
