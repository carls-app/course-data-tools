#!/usr/bin/env python3
""" Sonia Moreno, 9/2017
 Scrapes data from Carleton Enroll website containing course schedule information.
 """

from bs4 import BeautifulSoup
from argparse import ArgumentParser
from urllib.parse import parse_qs
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import itertools
import requests
import re
import sys
import time
import json
from pathlib import Path
import datetime


def discover_terms(*, first, last):
    term_names = ['FA', 'WI', 'SP']

    first = first if first else ''
    last = last if last else ''

    first_year, first_sem = first[:2], first[2:]
    last_year, last_sem = last[:2], last[2:]

    if first_year:
        first_year = f'20{first_year}' if first_year < '90' else f'19{first_year}'
    if last_year:
        last_year = f'20{last_year}' if last_year < '90' else f'19{last_year}'

    first_year = int(first_year) if first_year else datetime.date.today().year - 4
    last_year = int(last_year) if last_year else datetime.date.today().year

    for y in range(first_year, last_year + 1):
        terms = term_names

        if y == first_year and first_sem:
            terms = term_names[term_names.index(first_sem):]
        elif y == last_year and last_sem:
            terms = term_names[:term_names.index(last_sem)]

        for t in terms:
            yield f'{str(y)[2:]}{t}'


def fetch_academic_terms():
    """ Returns list of academic terms that user can choose from. Item in list
    will be passed to function that returns html link with term info provided.
    Example: 'term=18WI' in 'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term=18WI&subject=CS'
    """

    # Homepage showing listings of academic terms and course subjects
    html_enroll = requests.get('https://apps.carleton.edu/campus/registrar/schedule/enroll/').text
    soup = BeautifulSoup(html_enroll, 'html5lib')

    # Tag object containing list of academic terms
    term_summary = soup.find("select", id="termElement")

    # Each term name such as "Winter 2018" has tag "option"
    terms = term_summary.find_all("option")

    # We want the value attribute; example: <option value="18WI">
    # Create list with all value attributes; this will be list of terms available to choose from
    return [opt['value'] for opt in terms]


def fetch_subjects():
    """ Returns list of course subjects. Each will be passed to function that returns
    appropriate html link which contains specific course information for the subject
    Example: 'subject=CS' in 'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term=18WI&subject=CS'
    """
    html_enroll = requests.get('https://apps.carleton.edu/campus/registrar/schedule/enroll/').text
    soup2 = BeautifulSoup(html_enroll, 'html5lib')

    # Tag object containing list of subjects
    subject_summary = soup2.find("select", id="subjectElement")

    # Each subject within summary has tag "option"
    # Create a list with subjects, excluding 'Selected' tag (1st item)
    subjects = subject_summary.find_all("option")[1:]

    # Only get the associated text, excluding the tag itself and add them to list
    subj_list = []
    for item in subjects:
        subj_list.append(item.get_text())

    # print subj_list

    # Each item in subj_list is currently in the form: 'Computer Science (CS)'
    # We only want the abbreviation in the parentheses so that we can use this in the html link
    # We use regular expressions to achieve this.
    subj_abbrev = []
    for i in subj_list:
        subj_abbrev.append(re.search('\((.*?)\)', i).group(1))

    # print subj_abbrev

    return subj_abbrev


def process_course(course):
    course_num = course.select_one(".coursenum")

    # Split apart the deptnum
    department, number = course_num.get_text().strip().split(' ')

    # Finds title attribute within each course
    # Only takes the actual name of the course, which is next to the coursenum attribute
    # but not within its own tag
    title = course.select_one(".title .coursenum").next_sibling.strip()

    # Find the teachers
    if course.select(".faculty"):
        instructors = [' '.join(inst.get_text().strip().split()) for inst in course.select(".faculty a")]
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
    prereq = str(course.select_one('.prereq')).strip() or None

    # and the comments
    comments = [el.get_text().strip() for el in course.select('.comments')]

    # Extract the course status
    status = course.select_one('.statusName').get_text().strip().strip(':')

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
        tags = [{**tag, 'code': tag['code'][0] if len(tag['code']) else None}
                for tag in tags]
    else:
        tags = []

    if course.select_one('.codes.overlays'):
        requirements = [{
            'name': code.get_text().strip(),
            'code': parse_qs(code.get('href')).get('requirements[]', []),
        } for code in course.select('.codes.overlays a')]
        requirements = [{**req, 'code': req['code'][0] if len(req['code']) else None}
                        for req in requirements]
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

    if course.select_one('.schedule'):
        # Start and end times for courses that have set times
        # Account for classes without set times
        schedule = course.select_one('.schedule')

        locations = [a.get_text().strip() for a in course.select('.locations a')]

        # there is at least one course that occurs on Saturday
        days = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
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
        'id': f'{department} {number}',
        'title': title,
        'department': department,
        'number': number,
        'instructors': instructors,
        'summary': summary,
        'prerequisites': prereq,
        'comments': comments,
        'credits': credit_count,
        'offerings': offerings,
        'requirements': requirements,
        'scnc': scnc,
        'size': size,
        'status': status,
        'synonym': synonym,
        'tags': tags,
    }


def clean_html(html):
    # Clean up the returned HTML to optimize storage size
    soup = BeautifulSoup(html, 'html5lib')

    # only save the enroll data
    soup = soup.select_one('#enrollModule')

    # remove the "my courses" block
    if soup.select_one('#myCourses'):
        soup.select_one('#myCourses').decompose()

    # remove the search form at the bottom
    if soup.select_one('#disco_form'):
        soup.select_one('#disco_form').decompose()

    return soup.prettify()


def fetch_subject_for_term(*, term, subject):
    html_string = f'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term={term}&subject={subject}'

    # Course listings for subject during term provided
    html = requests.get(html_string).text

    return clean_html(html)


def extract_courses(*, html):
    """ Returns dict object with course number, course name, and start/end times for each course
    Finds course info based on the academic term and subject chosen (in this case, Winter 2018)
    """
    soup = BeautifulSoup(html, 'html5lib')

    # Creates list of all items with course as class attribute, excluding related courses
    exact_courses_list = soup.select_one('#enrollModule .courses')
    courses = exact_courses_list.select('.course') if exact_courses_list else []
    for course in courses:
        yield process_course(course)


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
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {}
        for term, subject in itertools.product(args.terms, args.subjects):
            key = executor.submit(fetch_and_save,
                                  term=term,
                                  subject=subject,
                                  root=root,
                                  delay=args.delay)

            futures[key] = f'{term}/{subject}'

        for future in as_completed(futures):
            ident = futures[future]

            # noinspection PyBroadException
            try:
                data = future.result()
            except Exception as e:
                print(f'{ident} generated an exception: {e}')
            else:
                print(f'{ident} page is {len(data)} bytes')


def clean_and_save(*, path: Path):
    with open(path, 'r') as infile:
        html = infile.read()

    cleaned = clean_html(html)

    with open(path, 'w') as outfile:
        outfile.write(cleaned)


def cmd_clean(*, args, root):
    index_dir = root / 'indices'

    with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
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


def extract_and_save(*, html_file: Path, out_dir: Path):
    with open(html_file, 'r') as infile:
        html = infile.read()

    out_dir.mkdir(parents=True, exist_ok=True)

    for course in extract_courses(html=html):
        with open(out_dir / f'{course["id"]}.json', 'w') as outfile:
            json.dump(course, outfile, indent='\t', sort_keys=True)
            outfile.write('\n')


def cmd_extract(*, args, root):
    index_dir = root / 'indices'
    files_dir = root / 'courses'

    with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
        futures = {}
        for subject_dir in [d for d in index_dir.glob('*/*') if d.is_dir()]:
            html_file = subject_dir / '_index.html'

            term = subject_dir.parent.name
            subject = subject_dir.name

            if term not in args.terms:
                continue

            out_dir = files_dir / term / subject

            key = executor.submit(extract_and_save, html_file=html_file, out_dir=out_dir)

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


def cmd_bundle(*, args, root):
    terms = {}

    files_dir = root / 'courses'
    for term in [d for d in files_dir.glob('*') if d.is_dir()]:
        subjects = {}

        for subject in [d for d in term.glob('*') if d.is_dir()]:
            print(f'bundling term "{term.name}", subject "{subject.name}"', file=sys.stderr)

            filenames = [file for file in subject.glob('*.json')]

            courses = []
            for file in filenames:
                with open(file, 'r') as infile:
                    courses.append(json.load(infile))

            subjects[subject.name] = courses

        terms[term.name] = subjects

    with open(root / 'all.json', 'w') as outfile:
        print(f'saving all-term bundle')
        json.dump(terms, outfile, indent='\t', sort_keys=True)
        outfile.write('\n')


def main():
    parser = ArgumentParser()
    parser.add_argument('command', action='store', choices=['fetch', 'clean', 'extract', 'bundle'],
                        help='Which command to execute')
    parser.add_argument('terms', action='store', nargs='*', metavar='TERM',
                        help='A term, like 18WI or 15SP')
    parser.add_argument('--dest', action='store',
                        help='The folder to output data files to', default='../course-data')
    parser.add_argument('--subjects', action='store', type=lambda x: x.split(','),
                        help='If given, only fetch these subjects (e.g., WGST,CS')
    parser.add_argument('--print-subjects', action='store_true',
                        help='Print the known subjects, then exit')
    parser.add_argument('--print-terms', action='store_true',
                        help='Print the known terms, then exit')
    parser.add_argument('--delay', action='store', type=int, default=1,
                        help='Control the delay between term/subject fetches, in seconds (be nice)')
    parser.add_argument('--first-term', action='store', metavar='TERM',
                        help='Fetch terms from the given term until --last-term')
    parser.add_argument('--last-term', action='store', metavar='TERM',
                        help='Fetch terms from --first-term until the given term')

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
        cmd_fetch(args=args, root=root)
    if args.command == 'clean':
        cmd_clean(args=args, root=root)
    elif args.command == 'extract':
        cmd_extract(args=args, root=root)
    elif args.command == 'bundle':
        cmd_bundle(args=args, root=root)


if __name__ == '__main__':
    main()
