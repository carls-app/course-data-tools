#!/bin/bash -ve
cd course-data

# update course data files
# seq -w prints the leading zeros
# tail -c3 gets us the last "3" chars of the year: 1,8,\n
function terms() {
    for y in 99 $(seq -w 00 $(date +%Y | tail -c3)); do
        for s in WI SP FA; do
            echo "$y$s"
        done
    done
}

# -n1 to only pass one argument from stdin to the process
# -P2 to run 2 concurrent fetch processes
terms | xargs -t -n1 -P2 -- python3 ../read-enroll.py fetch
terms | xargs -t -n1 -P2 -- python3 ../read-enroll.py extract

git add .
git commit -m "course data update $(date)" || (echo "No updates found." && exit 0)
git push "https://$GITHUB_OAUTH@github.com/carls-app/course-data.git" master
