#!/bin/bash -ve
cd course-data

# update course data files
for y in $(seq 1999 $(date +%Y)); do
    for s in WI SP FA; do
        echo "$y$s"
    done
    # -n1 to only pass one argument from stdin to the process
    # -P3 to run 3 concurrent fetch processes
done | xargs -t -n1 -P3 -- pipenv run ../read-enroll.py fetch
pipenv run ../read-enroll.py extract

git add .
git commit -m "course data update $(date)" || (echo "No updates found." && exit 0)
git push "https://$GITHUB_OAUTH@github.com/carls-app/course-data.git" master
