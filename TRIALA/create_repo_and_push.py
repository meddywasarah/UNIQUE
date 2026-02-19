import os
import sys
import json
import base64
import urllib.request
import urllib.error


API = 'https://api.github.com'

def api_request(method, path, token, data=None):
    url = API + path
    headers = {'Authorization': f'token {token}', 'User-Agent': 'repo-uploader'}
    if data is not None:
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f'HTTPError {e.code} for {method} {path}: {body}')
        sys.exit(1)


def get_user(token):
    return api_request('GET', '/user', token)


def create_repo(token, name, private):
    payload = {'name': name, 'private': private}
    return api_request('POST', '/user/repos', token, payload)


def upload_file(token, owner, repo, path, content_bytes, message):
    b64 = base64.b64encode(content_bytes).decode('utf-8')
    payload = {'message': message, 'content': b64}
    api_path = f'/repos/{owner}/{repo}/contents/{path}'
    return api_request('PUT', api_path, token, payload)


def should_skip(path):
    parts = path.split(os.sep)
    if '.git' in parts:
        return True
    if parts[0] == 'venv' or parts[0] == '.venv':
        return True
    if any(p in ('.venv', '__pycache__') for p in parts):
        return True
    # skip large or generated logs
    if path.endswith('.log'):
        return True
    return False


def main():
    if len(sys.argv) < 3:
        print('Usage: create_repo_and_push.py <repo-name> <public|private>')
        sys.exit(1)
    repo_name = sys.argv[1]
    visibility = sys.argv[2].lower()
    private = visibility != 'public'

    token = os.environ.get('GHTOKEN')
    if not token:
        print('GHTOKEN environment variable not set')
        sys.exit(1)

    user = get_user(token)
    owner = user.get('login')
    print(f'Authenticated as {owner}')

    # create repo
    print(f'Creating repository {owner}/{repo_name} (private={private})')
    create_repo(token, repo_name, private)
    print('Repository created.')

    # walk files
    root = os.getcwd()
    for dirpath, dirnames, filenames in os.walk(root):
        # compute relative dir
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == '.':
            rel_dir = ''
        # skip .git
        if rel_dir.startswith('.git') or rel_dir == '.git':
            continue
        for fname in filenames:
            rel_path = os.path.join(rel_dir, fname) if rel_dir else fname
            # normalize to posix for GitHub
            github_path = rel_path.replace('\\', '/')
            if should_skip(rel_path):
                print('skip', github_path)
                continue
            full_path = os.path.join(dirpath, fname)
            try:
                with open(full_path, 'rb') as f:
                    data = f.read()
            except Exception as e:
                print(f'Failed to read {full_path}: {e}')
                continue
            print(f'Uploading {github_path} ({len(data)} bytes)')
            upload_file(token, owner, repo_name, github_path, data, f'Add {github_path}')
    print('All files uploaded.')

if __name__ == '__main__':
    main()
