#!/bin/bash -ve
cd course-data

# prepare the gh-pages branch
git checkout -B gh-pages master --no-track

# update bundled information for public consumption
python3 ../read-enroll.py --dest ./ bundle

# remove the source files (quietly)
git rm -rf --quiet indices/

# and … push
git add --all ./
git commit -m "course data bundles" --quiet
git push -f "https://$GITHUB_OAUTH@github.com/carls-app/course-data.git" gh-pages
