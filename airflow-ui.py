import platform
import shutil
import subprocess
import os
import uuid
import docker
from flask import Flask, render_template, request, redirect, url_for


app = Flask(__name__)

# Detect OS type (for future package installations)
def get_os_family():
    if os.path.exists("/etc/debian_version"):
        return "debian"
    elif os.path.exists("/etc/redhat-release"):
        return "redhat"
    else:
        return "unknown"

# Install missing package
def install_package(tool, os_family):
    try:
        if os_family == "debian":
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", tool], check=True)
        elif os_family == "redhat":
            subprocess.run(["sudo", "yum", "install", "-y", tool], check=True)
        return True, None
    except Exception as e:
        return False, str(e)

# Check if Portainer is actually installed and running (or exists as a container)
def is_portainer_installed():
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "portainer"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip() in ["true", "false"]
    except Exception:
        return False

# Actually run Portainer
def run_portainer():
    try:
        subprocess.run(["docker", "volume", "create", "portainer_data"], check=True)
        subprocess.run([
            "docker", "run", "-d",
            "-p", "9443:9443", "-p", "9000:9000",
            "--name", "portainer",
            "--restart=always",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", "portainer_data:/data",
            "portainer/portainer-ce:latest"
        ], check=True)
        return True, "✅ Portainer installed successfully."
    except subprocess.CalledProcessError as e:
        return False, f"❌ Docker Error: {str(e)}"

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/install_portainer", methods=["GET", "POST"])
def install_portainer_route():
    installed = is_portainer_installed()
    portainer_url = "https://localhost:9443"
    message = None

    if request.method == "POST":
        if not installed:
            success, message = run_portainer()
            installed = success
        else:
            message = "ℹ️ Portainer is already installed."

    return render_template("portainer.html", installed=installed, message=message, url=portainer_url)

@app.route("/pre-req")
def prereq():
    tools = ["pip3", "podman", "openssl", "docker"]
    results = {}
    os_family = get_os_family()

    for tool in tools:
        if shutil.which(tool):
            results[tool] = "✅ Installed"
        else:
            success, error = install_package(tool, os_family)
            if success:
                results[tool] = "❌ Not Found → 🛠️ Installed"
            else:
                results[tool] = f"❌ Not Found → ❌ Error: {error}"
    docker_installed = shutil.which("docker") is not None
    return render_template("prereq.html", results=results, os_family=os_family, docker_installed=docker_installed)


##################ANSIBLE INSTALLATION##################

@app.route("/airflow")
def ansible_info():
    return render_template("airflow_info.html")




@app.route("/airflow/setup")
def airflow_setup():
    try:
        output_logs = ""

        # Check if Docker is installed
        try:
            docker_version = subprocess.check_output(["docker", "--version"], stderr=subprocess.STDOUT).decode()
            output_logs += f"🐳 Docker found: {docker_version}\n"
        except FileNotFoundError:
            return render_template("airflow_setup.html", result="❌ Docker is not installed.")

        # Check if Docker Compose is installed
        try:
            compose_version = subprocess.check_output(["docker-compose", "--version"], stderr=subprocess.STDOUT).decode()
            output_logs += f"📦 Docker Compose found: {compose_version}\n"
        except FileNotFoundError:
            return render_template("airflow_setup.html", result="❌ Docker Compose is not installed.")

        # Create airflow directory if not exists
        airflow_dir = "airflow"
        os.makedirs(airflow_dir, exist_ok=True)

        # Download docker-compose.yaml file
        compose_file_url = "https://airflow.apache.org/docs/apache-airflow/3.0.3/docker-compose.yaml"
        subprocess.run(["curl", "-LfO", compose_file_url], cwd=airflow_dir, check=True)
        output_logs += f"📥 Downloaded docker-compose.yaml into ./{airflow_dir}\n"

        # Initialize Airflow (create directories and set permissions)
        env_file = os.path.join(airflow_dir, ".env")
        if not os.path.exists(env_file):
            with open(env_file, "w") as f:
                f.write("AIRFLOW_UID=50000\n")
            output_logs += f"⚙️ Created .env file with default AIRFLOW_UID=50000\n"

        # Start Airflow with docker-compose
        subprocess.run(["docker-compose", "up", "-d"], cwd=airflow_dir, check=True)
        output_logs += "🚀 Airflow is starting on http://localhost:8080\n"
        output_logs += "🧑 Default login: username = airflow | password = airflow\n"

    except subprocess.CalledProcessError as e:
        output_logs += f"❌ Error:\n{e}\n\n{e.stderr if hasattr(e, 'stderr') else ''}"
    except Exception as ex:
        output_logs += f"⚠️ Unexpected error: {str(ex)}"

    return render_template("airflow_setup.html", result=output_logs)




@app.route("/ansible/execution-environment")
def ansible_exec_env():
    try:
        nav_version = ""
        builder_version = ""

        # Check if ansible-navigator is already installed
        try:
            nav_version = subprocess.check_output(["ansible-navigator", "--version"], stderr=subprocess.STDOUT).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            subprocess.run(["pip3", "install", "ansible-navigator"], check=True)
            nav_version = subprocess.check_output(["ansible-navigator", "--version"]).decode().strip()

        # Check if ansible-builder is already installed
        try:
            builder_version = subprocess.check_output(["ansible-builder", "--version"], stderr=subprocess.STDOUT).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            subprocess.run(["pip3", "install", "ansible-builder"], check=True)
            builder_version = subprocess.check_output(["ansible-builder", "--version"]).decode().strip()

        message = (
            "✅ Prerequisites for Ansible Execution Environment are ready.<br><br>"
            f"🧭 <strong>ansible-navigator</strong> version: <code>{nav_version}</code><br>"
            f"🏗️ <strong>ansible-builder</strong> version: <code>{builder_version}</code><br><br>"
            "ℹ️ You can now use <code>ansible-builder create</code> to generate a container definition and build it "
            "with <code>ansible-builder build</code>.<br>"
            "Use <code>ansible-navigator run</code> to execute playbooks inside your container-based EE."
        )

    except subprocess.CalledProcessError as e:
        message = f"❌ Error during setup:<br><code>{e}</code>"

    return render_template("ansible_exec_env.html", message=message)


########################ansible execution environment########################


####################add ansible worker node ###########################################



@app.route("/ansible/local/add_worker_nodes", methods=["GET", "POST"])
def add_worker_nodes():
    client = docker.from_env()
    message = ""
    existing = []

    # Step 1: List all existing worker nodes
    for container in client.containers.list(all=True):
        if container.name.startswith("ubuntu-node"):
            ports = container.attrs['NetworkSettings']['Ports']
            ssh_port = ports.get("22/tcp", [{}])[0].get("HostPort", "N/A")
            existing.append((container.name, ssh_port, container.status))

    # Step 2: Handle form actions
    if request.method == "POST":
        if "create" in request.form:
            try:
                count = int(request.form["count"])
                base_port = int(request.form["base_port"])
                host_group = request.form["host_group"]
                image = "arunvel1988/ansible_worker_node"
                created = []

                inventory_path = "inventory.ini"
                with open(inventory_path, "w") as f:
                    f.write(f"[{host_group}]\n")

                    for i in range(count):
                        unique_suffix = str(uuid.uuid4())[:8]
                        name = f"ubuntu-node{i+1}-{unique_suffix}"
                        host_port = base_port + i

                        client.containers.run(
                            image,
                            detach=True,
                            name=name,
                            hostname=name,
                            ports={"22/tcp": host_port}
                        )
                        created.append((name, str(host_port)))
                        f.write(
                            f"{name} ansible_host=127.0.0.1 ansible_port={host_port} "
                            f"ansible_user=arun ansible_password=arun "
                            f"ansible_python_interpreter=/usr/bin/python3 "
                            f"ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
                        )

                message += f"✅ Created {len(created)} new worker nodes.<br>"
                for name, port in created:
                    message += f"<code>{name}</code> → SSH Port: <strong>{port}</strong><br>"

                return redirect(url_for('add_worker_nodes'))

            except Exception as e:
                message = f"❌ Error creating worker nodes:<br><code>{e}</code>"

        elif "delete" in request.form:
            try:
                deleted = []
                for container in client.containers.list(all=True):
                    if container.name.startswith("ubuntu-node"):
                        container.remove(force=True)
                        deleted.append(container.name)

                # Remove inventory if exists
                if os.path.exists("inventory.ini"):
                    os.remove("inventory.ini")

                message = f"🗑️ Deleted {len(deleted)} worker nodes:<br>" + "<br>".join(deleted)
                return redirect(url_for('add_worker_nodes'))

            except Exception as e:
                message = f"❌ Error deleting worker nodes:<br><code>{e}</code>"

    return render_template("add_worker_nodes.html", message=message, existing=existing)


@app.route("/ansible/local/add_worker_nodes/run_test_playbook", methods=["GET","POST"])
def run_test_playbook():
    try:
        playbook_path = "test_playbook.yml"
        inventory_path = "inventory.ini"

        # Create the test playbook file
        with open(playbook_path, "w") as f:
            f.write("""
- name: Test connection to Docker container
  hosts: all
  gather_facts: false
  tasks:
    - name: Ping the container via SSH
      ansible.builtin.ping:
""")

        # Run the playbook
        result = subprocess.run(
            ["ansible-playbook", "-i", inventory_path, playbook_path],
            capture_output=True,
            text=True
        )

        # Format the output for HTML display
        return f"""
            <div style='padding:20px;font-family:monospace;background:#f8f9fa;'>
                <h4>✅ Playbook Execution Output</h4>
                <pre style='background:#e9ecef;border:1px solid #ccc;padding:10px;'>{result.stdout}</pre>
                <h4 style='color:red;'>Stderr (if any)</h4>
                <pre style='background:#fdd;border:1px solid #f99;padding:10px;color:red;'>{result.stderr}</pre>
                <br>
                <a href="/ansible/local/add_worker_nodes" class="btn btn-outline-primary">← Back</a>
                <a href="/ansible/local/playbooks" class="btn btn-outline-primary">← Playbooks</a>
                <a href="/ansible/local/tower" class="btn btn-outline-primary">← Ansible Tower</a>
            </div>
        """

    except Exception as e:
        return f"""
            <div style='padding:20px;font-family:monospace;background:#fff3cd;'>
                <h4>❌ Error Running Playbook</h4>
                <pre style='color:red;'>{str(e)}</pre>
                <a href="/ansible/local/add_worker_nodes" class="btn btn-outline-warning">← Back</a>
            </div>
        """



####################add ansible worker node ###########################################

@app.route("/ansible/local/add_worker_nodes/preview_playbook", methods=["GET"])
def preview_playbook():
    playbook_path = "test_playbook.yml"
    inventory_path = "inventory.ini"

    try:
        # Ensure the files exist
        if not os.path.exists(playbook_path) or not os.path.exists(inventory_path):
            return "<pre>❌ Playbook or inventory file not found.</pre>"

        with open(playbook_path, "r") as pb, open(inventory_path, "r") as inv:
            playbook_content = pb.read()
            inventory_content = inv.read()

        return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Preview Ansible Files</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    pre {{ background-color: #f8f9fa; padding: 10px; border: 1px solid #dee2e6; border-radius: 6px; }}
                    .btn-rounded {{ border-radius: 25px; }}
                    body {{ padding: 20px; font-family: monospace; }}
                </style>
            </head>
            <body>
                <h3>📘 Playbook Content</h3>
                <pre>{playbook_content}</pre>

                <h3>📒 Inventory File</h3>
                <pre>{inventory_content}</pre>

                <h4>❓ Does this look correct?</h4>
                <form method="POST" action="/ansible/local/add_worker_nodes/run_test_playbook">
                    <button type="submit" class="btn btn-success btn-rounded">✅ Yes, Run Test Playbook</button>
                </form>
                <br>
                <a href="/ansible/local/add_worker_nodes" class="btn btn-outline-secondary btn-rounded">← Cancel</a>
            </body>
            </html>
        """

    except Exception as e:
        return f"<pre>❌ Error displaying files:<br>{str(e)}</pre>"


######################################## playbooks #################################################



PLAYBOOKS_DIR = "./playbooks"
INVENTORY_FILE = os.path.join(PLAYBOOKS_DIR, "./../inventory.ini")

@app.route('/ansible/local/playbooks', methods=['GET', 'POST'])
def ansible_local_playbooks():
    # Playbook run
    if request.method == 'POST':
        selected_playbook = request.form.get('playbook')
        if selected_playbook:
            playbook_path = os.path.join(PLAYBOOKS_DIR, selected_playbook)
            try:
                result = subprocess.run(
                    ['ansible-playbook', '-i', INVENTORY_FILE, playbook_path],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                return render_template("playbook_output.html", output=result.stdout)
            except subprocess.CalledProcessError as e:
                return render_template("playbook_output.html", output=e.stdout)

    # List playbooks
    playbooks = [f for f in os.listdir(PLAYBOOKS_DIR)
                 if f.endswith(('.yml', '.yaml')) and os.path.isfile(os.path.join(PLAYBOOKS_DIR, f))]
    
    return render_template('playbooks_list.html', playbooks=playbooks)


from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
import subprocess

@app.route('/ansible/local/playbooks/view/<playbook_name>')
def view_playbook(playbook_name):
    safe_name = secure_filename(playbook_name)
    playbook_path = os.path.join(PLAYBOOKS_DIR, safe_name)

    if not os.path.exists(playbook_path):
        return f"<pre>Playbook not found: {safe_name}</pre>"

    try:
        with open(playbook_path, 'r') as f:
            content = f.read()
        return render_template('playbook_view.html', playbook_name=safe_name, content=content)
    except Exception as e:
        return f"<pre>Could not read playbook: {e}</pre>"



######################################## playbooks end  #################################################



######################### advanced playbook start #####################################################



ADVANCED_PLAYBOOKS_DIR = "./advanced-playbooks"
ADV_PLAYBOOK_FILE = os.path.join(ADVANCED_PLAYBOOKS_DIR, "playbook.yml")
ADV_INVENTORY_FILE = os.path.join(ADVANCED_PLAYBOOKS_DIR, "./../inventory.ini")
ADV_OUTPUT_FILE = os.path.join(ADVANCED_PLAYBOOKS_DIR, "advanced_playbook_output.yml")
ADV_README_FILE = os.path.join(ADVANCED_PLAYBOOKS_DIR, "README.md")


def get_directory_tree(path):
    tree = ""
    for root, dirs, files in os.walk(path):
        level = root.replace(path, "").count(os.sep)
        indent = "│   " * level + "├── "
        tree += f"{indent}{os.path.basename(root)}/\n"
        subindent = "│   " * (level + 1) + "├── "
        for f in files:
            tree += f"{subindent}{f}\n"
    return tree


@app.route('/ansible/local/playbooks/advanced-playbooks', methods=['GET', 'POST'])
def view_advanced_playbook():
    output = None
    dir_tree = None
    readme = None

    if request.method == 'POST':
        if 'run_playbook' in request.form:
            try:
                result = subprocess.run(
                    ['ansible-playbook', '-i', ADV_INVENTORY_FILE, ADV_PLAYBOOK_FILE],
                   
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True
                )
                with open(ADV_OUTPUT_FILE, 'w') as f:
                    f.write(result.stdout)
                output = result.stdout
            except subprocess.CalledProcessError as e:
                output = e.stdout

        elif 'show_tree' in request.form:
            dir_tree = get_directory_tree(ADVANCED_PLAYBOOKS_DIR)

        elif 'show_readme' in request.form and os.path.exists(ADV_README_FILE):
            with open(ADV_README_FILE, 'r') as f:
                readme = f.read()

    return render_template(
        'advanced_playbook_output.html',
        dir_tree=dir_tree,
        readme=readme,
        output=output
    )

######################### advanced playbook end #####################################################

#####################################################################################################
#ansible roles start


ROLES_DIR = "./roles"
INVENTORY_FILE = "./inventory.ini"
ROLE_PLAYBOOK_FILE = "./roles/role_playbook.yml"

def get_directory_tree(path):
    tree = ""
    for root, dirs, files in os.walk(path):
        level = root.replace(path, "").count(os.sep)
        indent = "│   " * level + "├── "
        tree += f"{indent}{os.path.basename(root)}/\n"
        subindent = "│   " * (level + 1) + "├── "
        for f in files:
            tree += f"{subindent}{f}\n"
    return tree

@app.route('/ansible/local/playbooks/roles', methods=['GET', 'POST'])
def manage_roles():
    message = None
    output = None
    dir_tree = None
    readme = None

    if request.method == 'POST':
        if 'create_role' in request.form:
            role_name = request.form.get('role_name')
            if role_name:
                subprocess.run(['ansible-galaxy', 'init', os.path.join(ROLES_DIR, role_name)])
                message = f"✅ Role '{role_name}' created."
            else:
                message = "⚠️ Role name required."

        elif 'install_role' in request.form:
            role_name = request.form.get('role_name')
            if role_name:
                subprocess.run(['ansible-galaxy', 'install', role_name, '-p', ROLES_DIR])
                message = f"✅ Role '{role_name}' installed from Galaxy."
            else:
                message = "⚠️ Role name required."

        elif 'show_tree' in request.form:
            dir_tree = get_directory_tree(ROLES_DIR)

        elif 'show_readme' in request.form:
            role_name = request.form.get('role_name')
            readme_path = os.path.join(ROLES_DIR, role_name, 'README.md')
            if os.path.exists(readme_path):
                with open(readme_path) as f:
                    readme = f.read()
            else:
                readme = "README.md not found."

        elif 'run_role' in request.form:
            role_name = request.form.get('role_name')
            if role_name:
                # Create a temporary playbook using the role
                with open(ROLE_PLAYBOOK_FILE, 'w') as f:
                    f.write(f"""---
- hosts: all
  become: true
  roles:
    - {role_name}
""")
                try:
                    result = subprocess.run(
                        ['ansible-playbook', '-i', INVENTORY_FILE, ROLE_PLAYBOOK_FILE],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=True
                    )
                    output = result.stdout
                except subprocess.CalledProcessError as e:
                    output = e.stdout
            else:
                message = "⚠️ Role name required to run playbook."

    return render_template(
        'role_manager.html',
        message=message,
        dir_tree=dir_tree,
        readme=readme,
        output=output
    )


################################### ansible role end #############################################################

########################## Ansible Tower ##########################################################


@app.route('/ansible/local/tower', methods=['GET', 'POST'])
def ansible_tower():
    output = None
    install_requested = False
    awx_cloned = os.path.exists('./awx')

    if request.method == 'POST':
        install_requested = True

        try:
            distro = platform.freedesktop_os_release().get("ID", "").lower()
            
            # 1. Install Docker if not present
            docker_check = subprocess.run(['which', 'docker'], stdout=subprocess.PIPE, text=True)
            if not docker_check.stdout.strip():
                if "ubuntu" in distro or "debian" in distro:
                    subprocess.run(['sudo', 'apt', 'update'])
                    subprocess.run(['sudo', 'apt', 'install', '-y', 'docker.io'])
                elif "centos" in distro or "rhel" in distro or "rocky" in distro or "fedora" in distro:
                    subprocess.run(['sudo', 'yum', 'install', '-y', 'docker'])
                else:
                    raise Exception(f"Unsupported distro: {distro}. Please install Docker manually.")

            # 2. Install docker-compose if not present
            compose_check = subprocess.run(['which', 'docker-compose'], stdout=subprocess.PIPE, text=True)
            if not compose_check.stdout.strip():
                subprocess.run([
                    'sudo', 'curl', '-SL',
                    'https://github.com/docker/compose/releases/download/v2.32.0/docker-compose-linux-x86_64',
                    '-o', '/usr/local/bin/docker-compose'
                ])
                subprocess.run(['sudo', 'chmod', '+x', '/usr/local/bin/docker-compose'])
                subprocess.run(['sudo', 'ln', '-sf', '/usr/local/bin/docker-compose', '/usr/bin/docker-compose'])

            # 3. Clone AWX repo and setup
            if not awx_cloned:
                subprocess.run(['git', 'clone', 'https://github.com/ansible/awx.git'])
                os.chdir('./awx')               
                os.chdir('./tools/docker-compose')
                subprocess.run(['cp', '.env.example', '.env'])

            # 4. Start AWX via docker-compose
            os.chdir('./awx/tools/docker-compose')
            subprocess.run(['docker-compose', 'up', '-d'])

            output = "✅ AWX (Ansible Tower) installed and started successfully!"
        except Exception as e:
            output = f"❌ Error during AWX setup: {str(e)}"

    return render_template(
        'ansible_tower.html',
        output=output,
        install_requested=install_requested
    )


########################## Ansible Tower  end ##########################################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
