#!/usr/bin/env python3
""" Sonia Moreno, 9/2017
 Scrapes data from Carleton Enroll website containing course schedule information.
 """

from bs4 import BeautifulSoup
from argparse import ArgumentParser
import requests
import re
import time
import json
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

        if y == first_year and first_sem and first_sem != terms[0]:
            terms = term_names[term_names.index(first_sem):]
        elif y == last_year and last_sem and last_sem != terms[-1]:
            terms = term_names[:term_names.index(last_sem)]

        for t in terms:
            yield f'{str(y)}{t}'


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


def fetch_courses(*, term, subject):
    """ Returns dict object with course number, course name, and start/end times for each course
    Finds course info based on the academic term and subject chosen (in this case, Winter 2018)
    """
    # Creates dict object with course number as key and list containing name and times for course as values
    course_info = []

    html_string = f'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term={term}&subject={subject}'

    # Course listings for subject during term provided
    html = requests.get(html_string).text

    soup = BeautifulSoup(html, 'html5lib')

    # Creates list of all items with course as class attribute, excluding related courses
    course_summary = soup.find_all("div", class_="course")
    for course in course_summary:
        course_num = course.find(class_="coursenum").get_text()

        # Finds title attribute within each course
        title = course.find(class_="title").get_text()

        # Only takes the actual name of the course, which is next to the coursenum attribute
        # but not within its own tag
        course_name = 'n/a'
        for _ in title:
            course_name = course.find(class_="coursenum").next_sibling

        if not course_name:
            raise Exception('no course name found!')

        # Add info to list associated with key
        specific_info = {}
        if course_num.find(subject) > -1:
            specific_info['course_num'] = course_num
            specific_info['title'] = course_name.strip()
            if course.find(class_="faculty") is not None:
                faculty = course.find(class_="faculty").get_text()
                specific_info['faculty'] = faculty.strip()
                if course.find(class_="faculty").next_sibling is not None:
                    summary = course.find(class_="faculty").next_sibling
                    specific_info['summary'] = str(summary)
                else:
                    specific_info['summary'] = "n/a"
            else:
                specific_info['faculty'] = "n/a"
            if course.find(class_="status") is not None:
                enrollment = course.find(class_="status").get_text()
                # specific_info['enrollment'] = enrollment
                registered = re.findall(r'(?<=Registered: ).*?(?=,)', enrollment)[0]
                size = re.findall(r'(?<=Size: ).*?(?=,)', enrollment)[0]
                # print registered
                specific_info['registered'] = registered
                specific_info['size'] = size
                # print enrollment
            else:
                specific_info['registered'] = "n/a"
                specific_info['size'] = "n/a"

            # Start and end times for courses that have set times
            # Account for classes without set times
            if course.find(class_="start") is not None:
                start_time = course.find("span", {"class": "start"}).get_text()
                end_time = course.find(class_="end").get_text()
                specific_info['start_time'] = start_time
                specific_info['end_time'] = end_time
            else:
                specific_info['start_time'] = "n/a"
                specific_info['end_time'] = "n/a"

            course_info.append(specific_info)

    return course_info


def main():
    parser = ArgumentParser()
    parser.add_argument('TERM', action='store', nargs='*', metavar='TERM',
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
    parser.add_argument('--first-term', action='store', default='99WI', metavar='TERM',
                        help='Fetch terms from the given term until --last-term')
    parser.add_argument('--last-term', action='store', metavar='TERM',
                        help='Fetch terms from --first-term until the given term')

    args = parser.parse_args()
    args.terms = args.TERM

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

    for term in args.terms:
        for subject in args.subjects:
            print(f'fetching term "{term}", subject "{subject}"')

            course_info = fetch_courses(term=term, subject=subject)

            with open(f'../course-data/{term}-{subject}.json', 'w') as outfile:
                json.dump(course_info, outfile)

            time.sleep(args.delay)


if __name__ == '__main__':
    main()
