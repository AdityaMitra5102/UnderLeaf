import os
import tempfile
import shutil
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from requests_oauthlib import OAuth2Session
import requests
import base64
import zipfile
import io

# Allow OAuth over HTTP for local development (REMOVE IN PRODUCTION)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
# Add session configuration for better reliability
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True  # Set to True if using HTTPS

# Configure MikTeX on startup (Windows only)
if os.name == 'nt':  # Windows
    try:
        # Set auto-install mode
        subprocess.run(['initexmf', '--set-config-value', '[MPM]AutoInstall=1'], 
                      capture_output=True, check=False)
        # Enable auto-admin mode
        subprocess.run(['initexmf', '--set-config-value', '[MPM]AutoAdmin=1'], 
                      capture_output=True, check=False)
        # Update package database
        subprocess.run(['mpm', '--update-db'], 
                      capture_output=True, check=False)
        print("MikTeX configured for auto-package installation")
    except Exception as e:
        print(f"MikTeX configuration skipped: {e}")
        pass  # MikTeX might not be installed or configured
# GitHub OAuth settings
# GitHub OAuth settings
CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', 'Ov23liZ0MpNVP80jwhk9')
CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '06d97b6b9b83225862dfe782b01f797b9bcd9b6b')

AUTHORIZATION_BASE_URL = 'https://github.com/login/oauth/authorize'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
REDIRECT_URI  = os.environ.get('REDIRECT_URI', 'https://cryptane-underleaf.hf.space/callback')

@app.route('/')
def index():
    if 'oauth_token' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    github = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=['repo'])
    authorization_url, state = github.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    # Check if state exists in session
    if 'oauth_state' not in session:
        return redirect(url_for('login'))
    
    github = OAuth2Session(CLIENT_ID, state=session['oauth_state'], redirect_uri=REDIRECT_URI)
    
    try:
        token = github.fetch_token(TOKEN_URL, client_secret=CLIENT_SECRET, authorization_response=request.url)
        session['oauth_token'] = token['access_token']
        return redirect(url_for('index'))
    except Exception as e:
        print(f"OAuth error: {e}")
        return redirect(url_for('login'))

@app.route('/api/user')
def get_user():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    response = requests.get('https://api.github.com/user', headers=headers)
    return jsonify(response.json())

@app.route('/api/repos')
def get_repos():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    response = requests.get(f'https://api.github.com/user/repos?per_page={per_page}&page={page}&sort=updated', headers=headers)
    return jsonify(response.json())

@app.route('/api/branches/<path:repo>')
def get_branches(repo):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    response = requests.get(f'https://api.github.com/repos/{repo}/branches', headers=headers)
    
    branches = response.json()
    
    # If repo has no branches, create main branch
    if isinstance(branches, list) and len(branches) == 0:
        # Create an initial commit to main branch
        try:
            # Create a README.md file to initialize the repo
            content_txt='''# 🍃 UnderLeaf

This repository contains an UnderLeaf project. 

If this is not your project, fork it to start editing it.

Visit [underleaf.pages.dev](https://underleaf.pages.dev) to start using it.
            '''
            readme_content = base64.b64encode(content_txt.encode()).decode('utf-8')
            
            create_response = requests.put(
                f'https://api.github.com/repos/{repo}/contents/README.md',
                headers=headers,
                json={
                    'message': 'Initial commit',
                    'content': readme_content,
                    'branch': 'main'
                }
            )
            
            if create_response.status_code == 201:
                # Return the newly created main branch
                return jsonify([{'name': 'main'}])
        except Exception as e:
            print(f"Error creating main branch: {e}")
    
    return jsonify(branches)

@app.route('/api/tree/<path:repo>/<branch>')
def get_tree(repo, branch):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    # Get branch SHA
    branch_response = requests.get(f'https://api.github.com/repos/{repo}/git/ref/heads/{branch}', headers=headers)
    if branch_response.status_code != 200:
        return jsonify({'error': 'Branch not found'}), 404
    
    sha = branch_response.json()['object']['sha']
    
    # Get recursive tree
    tree_response = requests.get(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1', headers=headers)
    return jsonify(tree_response.json())

@app.route('/api/file', methods=['POST'])
def get_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    filepath = data['filepath']
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    url = f'https://api.github.com/repos/{repo}/contents/{filepath}?ref={branch}'
    
    print(f"Fetching: {url}")  # Debug line
    response = requests.get(url, headers=headers)
    
    print(f"Status: {response.status_code}")  # Debug line
    
    if response.status_code != 200:
        print(f"Error: {response.text}")  # Debug line
        return jsonify({'error': 'File not found'}), 404
    
    if response.status_code != 200:
        return jsonify({'error': 'File not found'}), 404
    
    data = response.json()
    
    # Decode content if it's a file
    if data.get('type') == 'file' and 'content' in data:
        try:
            content = base64.b64decode(data['content']).decode('utf-8')
            print(f"Text file: {filepath}")
            return jsonify({'content': content, 'sha': data['sha'], 'type': 'text'})
        except UnicodeDecodeError:
            # Binary file - return base64 as-is
            print(f"Binary file: {filepath}")
            return jsonify({'content': data['content'], 'sha': data['sha'], 'type': 'binary'})
    
    return jsonify(data)

@app.route('/api/save', methods=['POST'])
def save_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    filepath = data['filepath']
    content = data['content']
    sha = data.get('sha')
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    # Create commit message with timestamp
    commit_message = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Encode content
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    payload = {
        'message': commit_message,
        'content': encoded_content,
        'branch': branch
    }
    
    if sha:
        payload['sha'] = sha
    
    response = requests.put(
        f'https://api.github.com/repos/{repo}/contents/{filepath}',
        headers=headers,
        json=payload
    )
    
    if response.status_code in [200, 201]:
        return jsonify({'success': True, 'sha': response.json()['content']['sha']})
    else:
        return jsonify({'error': response.json()}), response.status_code

@app.route('/api/create', methods=['POST'])
def create_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    filepath = data['filepath']
    content = data.get('content', '')
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    commit_message = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    payload = {
        'message': commit_message,
        'content': encoded_content,
        'branch': branch
    }
    
    response = requests.put(
        f'https://api.github.com/repos/{repo}/contents/{filepath}',
        headers=headers,
        json=payload
    )
    
    if response.status_code == 201:
        return jsonify({'success': True, 'sha': response.json()['content']['sha']})
    else:
        return jsonify({'error': response.json()}), response.status_code

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    filepath = data['filepath']
    content = data['content']  # Already base64 encoded from frontend
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    commit_message = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    payload = {
        'message': commit_message,
        'content': content,  # Use as-is since it's already base64
        'branch': branch
    }
    
    response = requests.put(
        f'https://api.github.com/repos/{repo}/contents/{filepath}',
        headers=headers,
        json=payload
    )
    
    if response.status_code == 201:
        return jsonify({'success': True, 'sha': response.json()['content']['sha']})
    else:
        return jsonify({'error': response.json()}), response.status_code

@app.route('/api/compile', methods=['POST'])
def compile_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    filepath = data['filepath']
    commit = data.get('commit')
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Clone repository
        clone_url = f"https://{session['oauth_token']}@github.com/{repo}.git"
        
        if commit:
            # Clone and checkout specific commit
            subprocess.run(['git', 'clone', clone_url, temp_dir], 
                          check=True, capture_output=True)
            subprocess.run(['git', 'checkout', commit], 
                          cwd=temp_dir, check=True, capture_output=True)
        else:
            # Clone specific branch
            subprocess.run(['git', 'clone', '-b', branch, '--depth', '1', clone_url, temp_dir], 
                          check=True, capture_output=True)
        
        # Full path to file
        file_path = os.path.join(temp_dir, filepath)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found in repository'}), 404
        
        # Get the directory where the file is located
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        
        # Use file's directory as working directory (or temp_dir if file is at root)
        working_dir = file_dir if file_dir else temp_dir
        
        # Detect file type and choose appropriate compilation
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Configure environment for MikTeX
        env = os.environ.copy()
        env['MIKTEX_AUTOINSTALL'] = 'yes'  # Auto-install missing packages
        
        if file_ext in ['.tex', '.latex']:
            # For LaTeX files, compile directly with pdflatex/xelatex
            # Output PDF will be in the same directory as the source file
            output_pdf = os.path.join(working_dir, os.path.splitext(file_name)[0] + '.pdf')
            
            # Run twice for references and TOC
            for i in range(2):
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', file_name],
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    env=env
                )
        else:
            # For other formats (Markdown, etc.), use Pandoc
            # Output in same directory as source
            output_pdf = os.path.join(working_dir, os.path.splitext(file_name)[0] + '.pdf')
            result = subprocess.run(
                ['pandoc', file_name, '-o', os.path.basename(output_pdf), '--pdf-engine=xelatex'],
                cwd=working_dir,
                capture_output=True,
                text=True,
                env=env
            )
        
        # Don't check return code - only check if PDF exists
        # This handles cases where compilers return non-zero but still produce PDFs
        
        # Check if PDF was actually created
        if not os.path.exists(output_pdf):
            return jsonify({'error': f'Compilation failed: PDF not generated.\n\n{result.stderr}'}), 400
        
        # Read PDF and encode to base64
        with open(output_pdf, 'rb') as f:
            pdf_content = base64.b64encode(f.read()).decode('utf-8')
        
        return jsonify({'success': True, 'pdf': pdf_content})
        
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'Git/Pandoc error: {e.stderr.decode()}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/api/upload-zip', methods=['POST'])
def upload_zip():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    branch = data['branch']
    zip_data = data['zip_data']
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    try:
        # 1. Decode and unzip in memory
        zip_bytes = base64.b64decode(zip_data)
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
        
        # 2. Get current branch SHA
        ref_res = requests.get(f'https://api.github.com/repos/{repo}/git/ref/heads/{branch}', headers=headers)
        base_sha = ref_res.json()['object']['sha']
        
        # 3. Create Blobs for each file
        tree_items = []
        files_processed = 0
        
        for file_info in z.infolist():
            if file_info.is_dir():
                continue
                
            with z.open(file_info) as f:
                content = f.read()
                # Handle both text and binary files via base64
                encoded_content = base64.b64encode(content).decode('utf-8')
                
                blob_res = requests.post(
                    f'https://api.github.com/repos/{repo}/git/blobs',
                    headers=headers,
                    json={'content': encoded_content, 'encoding': 'base64'}
                )
                
                if blob_res.status_code == 201:
                    tree_items.append({
                        "path": file_info.filename,
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_res.json()['sha']
                    })
                    files_processed += 1

        if not tree_items:
            return jsonify({'error': 'No files found in zip'}), 400

        # 4. Create a new Tree
        tree_res = requests.post(
            f'https://api.github.com/repos/{repo}/git/trees',
            headers=headers,
            json={'base_tree': base_sha, 'tree': tree_items}
        )
        new_tree_sha = tree_res.json()['sha']

        # 5. Create a Commit
        commit_res = requests.post(
            f'https://api.github.com/repos/{repo}/git/commits',
            headers=headers,
            json={
                'message': f'Upload zip archive ({files_processed} files) - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'tree': new_tree_sha,
                'parents': [base_sha]
            }
        )
        new_commit_sha = commit_res.json()['sha']

        # 6. Update Reference
        patch_res = requests.patch(
            f'https://api.github.com/repos/{repo}/git/refs/heads/{branch}',
            headers=headers,
            json={'sha': new_commit_sha}
        )

        return jsonify({'success': True, 'files_count': files_processed})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<path:repo>/<branch>')
def download_repo(repo, branch):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Return GitHub's zipball URL
    url = f'https://github.com/{repo}/archive/refs/heads/{branch}.zip'
    return jsonify({'url': url})

@app.route('/api/commits/<path:repo>/<branch>')
def get_commits(repo, branch):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    per_page = request.args.get('per_page', 50)
    headers = {'Authorization': f"token {session['oauth_token']}"}
    response = requests.get(f'https://api.github.com/repos/{repo}/commits?sha={branch}&per_page={per_page}', headers=headers)
    return jsonify(response.json())

@app.route('/api/delete', methods=['POST'])
def delete_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    # GitHub requires the file SHA to delete it
    payload = {
        'message': f"Delete {data['filepath']}",
        'sha': data['sha'],
        'branch': data['branch']
    }
    
    url = f"https://api.github.com/repos/{data['repo']}/contents/{data['filepath']}"
    response = requests.delete(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return jsonify({'success': True})
    return jsonify({'error': response.json()}), response.status_code

@app.route('/api/rename', methods=['POST'])
def rename_file():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    headers = {'Authorization': f"token {session['oauth_token']}"}
    repo = data['repo']
    branch = data['branch']
    
    # 1. Get the original file content
    get_url = f"https://api.github.com/repos/{repo}/contents/{data['old_path']}?ref={branch}"
    file_data = requests.get(get_url, headers=headers).json()
    
    # 2. Create the file at the new path
    create_payload = {
        'message': f"Rename {data['old_path']} to {data['new_path']}",
        'content': file_data['content'],
        'branch': branch
    }
    create_url = f"https://api.github.com/repos/{repo}/contents/{data['new_path']}"
    create_res = requests.put(create_url, headers=headers, json=create_payload)
    
    if create_res.status_code not in [200, 201]:
        return jsonify({'error': 'Failed to create new file'}), 500

    # 3. Delete the old file
    delete_payload = {
        'message': f"Cleanup after rename: {data['old_path']}",
        'sha': data['sha'],
        'branch': branch
    }
    delete_url = f"https://api.github.com/repos/{repo}/contents/{data['old_path']}"
    requests.delete(delete_url, headers=headers, json=delete_payload)
    
    return jsonify({'success': True})

@app.route('/api/commit-at-time/<path:repo>/<branch>/<timestamp>')
def get_commit_at_time(repo, branch, timestamp):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    from datetime import datetime as dt
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    # Get commits until the specified timestamp
    target_time = dt.fromisoformat(timestamp.replace('Z', '+00:00'))
    
    # Fetch commits (GitHub API returns newest first)
    response = requests.get(f'https://api.github.com/repos/{repo}/commits?sha={branch}&per_page=100', headers=headers)
    commits = response.json()
    
    # Find the first commit that's before or at the target time
    selected_commit = None
    for commit in commits:
        commit_time = dt.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00'))
        if commit_time <= target_time:
            selected_commit = commit
            break
    
    if selected_commit:
        return jsonify({'commit': selected_commit})
    else:
        return jsonify({'error': 'No commits found before this time'}), 404

@app.route('/api/tree-at-commit/<path:repo>/<commit_sha>')
def get_tree_at_commit(repo, commit_sha):
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    
    # Get commit
    commit_response = requests.get(f'https://api.github.com/repos/{repo}/git/commits/{commit_sha}', headers=headers)
    if commit_response.status_code != 200:
        return jsonify({'error': 'Commit not found'}), 404
    
    tree_sha = commit_response.json()['tree']['sha']
    
    # Get recursive tree
    tree_response = requests.get(f'https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1', headers=headers)
    return jsonify(tree_response.json())
        

@app.route('/api/file-at-commit', methods=['POST'])
def get_file_at_commit():
    if 'oauth_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    repo = data['repo']
    commit = data['commit']
    filepath = data['filepath']
    
    headers = {'Authorization': f"token {session['oauth_token']}"}
    response = requests.get(f'https://api.github.com/repos/{repo}/contents/{filepath}?ref={commit}', headers=headers)
    
    if response.status_code != 200:
        return jsonify({'error': 'File not found'}), 404
    
    file_data = response.json()
    
    # Decode content if it's a file
    if file_data.get('type') == 'file' and 'content' in file_data:
        try:
            content = base64.b64decode(file_data['content']).decode('utf-8')
            return jsonify({'content': content, 'sha': file_data['sha'], 'type': 'text'})
        except UnicodeDecodeError:
            # Binary file - return base64 as-is
            return jsonify({'content': file_data['content'], 'sha': file_data['sha'], 'type': 'binary'})
    
    return jsonify(file_data)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':

    app.run(debug=True, port=5000)