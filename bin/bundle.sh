#!/bin/bash -ve
cd course-data

# prepare the gh-pages branch
git checkout -B gh-pages master --no-track

# update bundled information for public consumption
pipenv run ../read-enroll.py bundle --out-dir ./ --format json --format csv

# remove the source files (quietly)
git rm -rf --quiet details/ raw_xml/

# and … push
git add --all ./
git commit -m "course data bundles" --quiet
git push -f "https://$GITHUB_OAUTH@github.com/carls-app/course-data.git" gh-pages
