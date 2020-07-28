import datetime
import os
import subprocess
from operator import itemgetter
from pathlib import Path
from subprocess import PIPE

import sys

HASH = 'hash'

TAG = 'tag'
TIMESTAMP = 'timestamp'


def error(message):
    print(message)

    write_logs()

    exit(1)


def init():
    if not os.path.isdir(root):
        error('The repository root \'' + root + '\' does not exist or is not a directory.')
    if not os.path.isdir(root + '/' + master_repository):
        error('The main repository \'' + root + '/' + master_repository + '\' does not exist or is not a directory.')


def log(data):
    if data.endswith('\n'):
        data = data.replace('\n', '')
    logs.append(data)


def write_logs():
    with open('logfile', 'w') as f:
        for line in logs:
            f.write(line + '\n')


def run_command(command, url):
    output = subprocess.Popen(command, stdout=PIPE, stderr=PIPE, cwd=url)

    command_str = 'COMMAND: \'' + url + '/' + ' '.join(command) + '\''

    log('*')
    log('* ' + command_str)
    log('* ' + '-' * len(command_str))
    log('*')

    command_output = []
    for line in output.stdout:
        line = os.fsdecode(line)
        log('* ' + line)
        command_output.append(line)
    for line in output.stderr:
        line = os.fsdecode(line)
        log('* ' + line)
        command_output.append(line)
    log('')

    return command_output


def retrieve_tags(url):
    log('')
    log('- Retrieve tags for \'' + url + '\'')
    log('')

    if not os.path.isdir(url + '/.git'):
        error('The URL \'' + url + '\' does not contain a git repository.')

    tags = []
    output = run_command(['git', 'log', '--tags', '--simplify-by-decoration', '--pretty=%ai %d %H'], url)
    for line in output:
        tokens = line.split()
        if len(tokens) > 4:
            index = tokens[-2].find(')')
            if index > 0:
                tags.append(
                    {TIMESTAMP: create_timestamp(tokens[0], tokens[1], tokens[2]),
                     TAG: tokens[-2][:index],
                     HASH: tokens[-1]})

    return tags


def find_commits(url):
    log('')
    log('- Find commits for \'' + url + '\'')
    log('')

    if not os.path.isdir(url + '/.git'):
        error('The URL \'' + url + '\' does not contain a git repository.')

    commits = []
    output = run_command(['git', 'log', '--date=iso', '--pretty=%H %ad'], url)
    for line in output:
        tokens = os.fsdecode(line).split()
        if len(tokens) > 3:
            commits.append({TIMESTAMP: create_timestamp(tokens[1], tokens[2], tokens[3]), 'hash': tokens[0]})

    return sorted(commits, key=itemgetter(TIMESTAMP))


def find_repositories(url):
    log('')
    log('- Find repositories in \'' + url + '\'')
    log('')

    if not os.path.isdir(url):
        error('The URL \'' + url + '\' does not exist or is not a directory.')

    repositories = []
    for entry in Path(url).iterdir():
        repository = str(entry)
        if os.path.isdir(repository + '/.git'):
            repositories.append(repository)

    repositories.append(root)

    return repositories


def find_last_commit(url, timestamp):
    commits = find_commits(url)

    last_commit = None
    for commit in commits:
        if commit[TIMESTAMP] > timestamp:
            return last_commit

        last_commit = commit

    return last_commit


def create_timestamp(date_str, time_str, timezone_str):
    year, month, day = date_str.split('-')
    hour, minute, second = time_str.split(':')

    timestamp = datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), 0)
    delta = datetime.timedelta(hours=int(timezone_str[0:3]))

    return timestamp - delta


def create_release_file(tag_str):
    log('')
    log('- Creating a release file for tag \'' + tag_str + '\'.')
    log('')

    restore_repositories()

    required_tag = None
    for tag in retrieve_tags(root + '/' + master_repository):
        if tag[TAG] == tag_str:
            required_tag = tag

    if required_tag is None:
        error('Could not find tag \'' + tag_str + '\'')

    filename = master_repository + '_' + tag_str
    with open(filename, 'w') as file:
        file.write(master_repository + ' ' + required_tag[HASH] + ' ' + str(required_tag[TIMESTAMP]) + '\n')
        for repository in find_repositories(root):
            new_line = repository.split('/')[-1]
            if new_line == master_repository:
                continue

            last_commit = find_last_commit(repository, required_tag[TIMESTAMP])

            if last_commit is None:
                new_line += ' N/A'
            else:
                new_line += ' ' + last_commit[HASH] + ' ' + str(last_commit[TIMESTAMP])
            file.write(new_line + '\n')

    print('Release file ' + filename + ' created.')


def update_release_file(tag, repository, which):
    restore_repositories()

    release_file = master_repository + '_' + tag

    if not os.path.isfile(release_file):
        error('The release file \'' + release_file + '\' does not exist or is not a file.')

    if which == 'next':
        delta = 1
    elif which == 'previous':
        delta = -1
    else:
        error('direction should be \'previous\' or \'next\'')

    log('')
    log('- Updating the release file \'' + release_file + '\': Use the ' + which + ' commit for .')
    log('')

    current_file = []
    repository_found = False
    with open(release_file) as file:
        line = file.readline()
        while len(line) > 0:
            current_file.append(line)
            if line.startswith(repository + ' '):
                repository_found = True
            line = file.readline()

    if not repository_found:
        error('Repository \'' + repository + '\' not found in release file.')

    new_file = []
    for line in current_file:
        tokens = line.split(' ')
        if tokens[0] == repository:
            commits = find_commits(root + '/' + repository)

            commit = None
            for index in range(len(commits)):
                if commits[index][HASH] == tokens[1]:
                    commit = commits[index + delta]

            if commit is None:
                print('The repository \'' + repository + '\' does not contain the commit \'' + tokens[1] + '\'')
                return

            new_line = repository + ' ' + commit[HASH] + ' ' + str(commit[TIMESTAMP]) + ' '
            if len(tokens) == 4:
                new_line += tokens[1]
            else:
                new_line += tokens[4]
            new_file.append(new_line + '\n')
        else:
            new_file.append(line)

    with open(release_file, 'w') as file:
        for line in new_file:
            file.write(line)

    print('The ' + repository + ' repository has been updated to use the ' + which + ' commit.')


def clean_repository(url):
    log('')
    log('- Cleaning the repository for \'' + url + '\'.')
    log('')

    if not os.path.isdir(url + '/.git'):
        error('The URL \'' + url + '\' does not contain a git repository.')

    command = ['git', 'clean', '-d', '-f', '-x']
    run_command(command, url)


def checkout_branch(url, hash):
    log('')
    log('- Checking out branch \'' + url + '\'.')
    log('')

    if not os.path.isdir(url + '/.git'):
        error('The URL \'' + url + '\' does not contain a git repository.')

    command = ['git', 'checkout', hash]
    run_command(command, url)


def prepare_repositories(release_file):
    log('')
    log('- Preparing the repositories using release file \'' + release_file + '\'.')
    log('')

    if not os.path.isfile(release_file):
        error('The release file \'' + release_file + '\' does not exist or is not a file.')

    with open(release_file) as file:
        line = file.readline()
        while len(line) > 0:
            parts = line.split(' ')
            clean_repository(root + '/' + parts[0])
            checkout_branch(root + '/' + parts[0], parts[1])
            line = file.readline()

    print('The repositories has been updated to match the commits specified in \'' + release_file + '\'.')


def restore_repositories():
    log('')
    log('- Restoring repositories.')
    log('')

    repositories = find_repositories(root)

    for repository in repositories:
        clean_repository(repository)
        checkout_branch(repository, 'master')


logs = []
root = 'libretro-super'
master_repository = 'retroarch'

init()

if sys.argv[1] == 'list':
    for tag in [tag['tag'] for tag in retrieve_tags(root + '/' + master_repository)]:
        print(tag)

if sys.argv[1] == 'create':
    create_release_file(sys.argv[2])

if sys.argv[1] == 'update':
    update_release_file(sys.argv[2], sys.argv[3], sys.argv[4])

if sys.argv[1] == 'prepare':
    prepare_repositories(sys.argv[2])

if sys.argv[1] == 'restore':
    restore_repositories()

write_logs()
