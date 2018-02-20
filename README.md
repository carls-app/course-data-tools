# course-data-tools

> Originally forked from <https://github.com/sonimore/CourseSchedulesApp/blob/master/ReadText.py>

This repository houses the scripts that manage the data in <https://github.com/carls-app/course-data>.

## Getting Started

First off, you'll need to get set up:

```
pip install pipenv
pipenv install
```

Next, this script assumes that you have the following folder structure:

```
root/  # name doesn't matter
    course-data/  # the course-data repo
    course-data-tools/  # this repo; name doesn't matter
```

Once you have that, the rest of these commands will operate on the sibling `course-data/` folder.

```
# to fetch all data
pipenv run ./read-enroll.py fetch --first-term 99WI

# to fetch recent data
pipenv run ./read-enroll.py fetch

# to fetch only a certain term
pipenv run ./read-enroll.py fetch 18SP
```

When you want to extract the couses from the HTML into the JSON files, do this:

```
# to extract all terms
pipenv run ./read-enroll.py extract

# to extract only a certain term
pipenv run ./read-enroll.py extract 18SP
```


## `read-enroll.py --help`
```
usage: read-enroll.py [-h] [--dest DEST] [--subjects SUBJECTS]
                      [--print-subjects] [--print-terms] [--delay DELAY]
                      [--first-term TERM] [--last-term TERM]
                      {fetch,clean,extract,bundle} [TERM [TERM ...]]

positional arguments:
  {fetch,clean,extract,bundle}
                        Which command to execute
  TERM                  A term, like 18WI or 15SP

optional arguments:
  -h, --help            show this help message and exit
  --dest DEST           The folder to output data files to
  --subjects SUBJECTS   If given, only fetch these subjects (e.g., WGST,CS
  --print-subjects      Print the known subjects, then exit
  --print-terms         Print the known terms, then exit
  --delay DELAY         Control the delay between term/subject fetches, in
                        seconds (be nice)
  --first-term TERM     Fetch terms from the given term until --last-term
  --last-term TERM      Fetch terms from --first-term until the given term
```
