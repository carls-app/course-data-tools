#!/usr/bin/env python2
""" Sonia Moreno, 9/2017
 Scrapes data from Carleton Enroll website containing course schedule information.
 """

from __future__ import print_function
from collections import defaultdict
from bs4 import BeautifulSoup
import requests
import re
import os
import time
import json


def academic_terms():
    """ Returns list of academic terms that user can choose from. Item in list
    will be passed to function that returns html link with term info provided.
    Example: 'term=18WI' in 'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term=18WI&subject=CS'
    """
    # Homepage showing listings of academic terms and course subjects
    html_enroll = requests.get('https://apps.carleton.edu/campus/registrar/schedule/enroll/').text
    soup2 = BeautifulSoup(html_enroll, 'html5lib')

    # Tag object containing list of academic terms
    term_summary = soup2.find("select", id="termElement")

    # Each term name such as "Winter 2018" has tag "option"
    terms = term_summary.find_all("option")

    # We want the value attribute; example: <option value="18WI">
    # Create list with all value attributes; this will be list of terms available to choose from
    term_list = []
    for option in terms:
        term_list.append(option['value'])
    return term_list


def get_subjects():
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


def fetch_term_info(term):
    """ Returns dict object with course number, course name, and start/end times for each course
    Finds course info based on the academic term and subject chosen (in this case, Winter 2018)
    """
    # Creates dict object with course number as key and list containing name and times for course as values
    course_info = defaultdict(list)

    for subject in get_subjects():
        html_string = 'https://apps.carleton.edu/campus/registrar/schedule/enroll/?term=%s&subject=%s' % (term, subject)

        # Course listings for subject during term provided
        print('fetching term "%s", subject "%s"' % (term, subject))
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
            for _ in title:
                course_name = course.find(class_="coursenum").next_sibling

            if not course_name:
                raise Exception('no course name found!')

            # Add info to list associated with key
            specific_info = {}
            if course_num.find(subject) > -1:
                specific_info['course_num'] = course_num
                specific_info['title'] = course_name
                if course.find(class_="faculty") is not None:
                    faculty = course.find(class_="faculty").get_text()
                    specific_info['faculty'] = faculty
                    if course.find(class_="faculty").next_sibling is not None:
                        summary = course.find(class_="faculty").next_sibling
                        summary = summary.encode("utf-8")
                        specific_info['summary'] = summary
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

                course_info['course_info'].append(specific_info)

        time.sleep(1)

    return course_info


def fetch_all_terms():
    """ Returns HTML string that Specific Course Info will use to provide information
    for every term and subject combination.
    """
    terms = academic_terms()
    for term in terms:
        course_info = fetch_term_info(term)
        with open('data/%s.json' % term, 'w') as outfile:
            json.dump(course_info, outfile)


def main():
    # print(academic_terms())
    fetch_all_terms()
    # fetch_term_info('18WI')


main()
