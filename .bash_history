to set your account's default identity.
Omit --global to set the identity only in this repository.

fatal: empty ident name (for <opcc@evcc.local>) not allowed
opcc@evcc:~$
exit
quit
git config --global user.email "andreas.spiess@rumba.com"
git config --global user.name "Andreas"
git commit -m "Initial project setup"
git remote add origin https://github.com/SensorsIot/OCPP-Tester.git
git push -u origin main
git branch
git push -u origin master
git branch
git push -u origin master
git push -u origin master
git push -u origin master
where
pwd
opcc@evcc:~$ pwd
/home/opcc
python3 -m venv venv
source venv/bin/activate
pip install websockets
pip install python-dateutil
mkdir app
touch app/__init__.py
touch app/server.py
touch app/handlers.py
touch app/messages.py
touch app/central_system.py
touch app/protocol.py
python main.py
python3 main.py
tree
cd app
ls
python3 main.py
cd ..
python3 main.py

python3 main.py
python3 main.py
python3 main.py
python3 main.py
python3 main.py
python3 main.py
clear
python3 main.py
python3 main.py
python3 main.py
python3 main.py
python3 main.py
python3 main.py
touch app/__init__.py
python3 main.py
python3 main.py
cd OPCC
python3 main.py
mv main.py app/
python3 main.py
cd app
python3 main.py
python3 main.py
cd ..
python3 -m app.main
cd app
ls
ls
cd ..
ls
cd OPCC
python3 main.py
cd opcc
python3 main.py
cd opcc
cd /home/opcc
python3 main.py
python3 main.py
pwd
python3 -m app.main
clear
cd /home/opcc
python3 main.py
python3 main.py
cd app
ls
cd ..
python3 main.py
python3 main.py
python3 main.py
git status
claer
clear
git status
git reset venv/
git reset venv/git add .
pwd
ls
nano .gitignore
git status
git add .gitignore
git commit -m "Add .gitignore to exclude common temporary and user files"
git status
git rm --cached .bash_history
git rm --cached .gitconfig
git rm --cached -r .cache/ # Use -r for directories
git commit -m "Stop tracking irrelevant user and cache files"
git add main.py app/ requirements.txt
git status
git commit -m "Add core application logic and dependencies"
clear
git status
git push origin master
git status
git add .
git commit -m "Your concise and descriptive commit message"
git push
git status
ssh-keygen -t ed25519 -C "your_email@example.com"
ssh-keygen -t ed25519 -C "andreas.spiess@arumba.com"
ls
ls -R
cd  .ssh
ls
cd ..
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
nano ~/.bashrc
source ~/.bashrc
ssh-add ~/.ssh/id_ed25519
ssh-add -l
cat ~/.ssh/id_ed25519.pub
git push origin master
git remote -v
git remote set-url origin git@github.com:SensorsIot/OCPP-Tester.git
git remote -v
git push origin master
git push origin master
python3 main.py
python3 main.py
python3 main.py
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
git status
git add .
git commit -m "working prototype"
git push
git status
git status
python3 main.py 
python3 main.py 
clear
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
git status
git add .
git commit -m "working prototype"
git push
git status
python3 main.py 
lo
exit
ls -ld ~/.ssh
ls -l ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
ls -l ~/.ssh/authorized_keys
ssh opcc@192.168.0.35
cat ~/.ssh/authorized_keys
sudo nano /etc/ssh/sshd_config
sudo nano /etc/ssh/sshd_config
sudo nano /etc/ssh/sshd_config
sudo systemctl restart ssh
exit
sudo apt-get update && sudo apt-get install openssh-server
sudo systemctl start sshd
sudo systemctl enable sshd
opcc@evcc:~$ sudo systemctl enable sshd
Failed to enable unit: Refusing to operate on alias name or linked unit file: sshd.service
opcc@evcc:~$
sudo systemctl stop ssh
sudo systemctl stop ssh
sudo systemctl enable ssh
sudo systemctl start ssh
ssh opcc@192.168.0.35
ssh opcc@192.168.0.35
exit
cat /etc/ssh/sshd_config
ls -l /etc/ssh/sshd_config.d/
sudo tail -f /var/log/auth.log
sudo tail -f /var/log/auth.log
sudo journalctl -u ssh -f
ls -ld ~
chmod go-w ~
exit
exit
ssh-copy-id -i C:\Users\AndreasSpiess\.ssh\id_rsa.pub opcc@192.168.0.35
ssh-copy-id -i C:\Users\AndreasSpiess\.ssh\id_rsa.pub opcc@192.168.0.35
ssh-copy-id -i C:\Users\AndreasSpiess\.ssh\id_rsa.pub opcc@192.168.0.35
python3 main.y
python3 main.py
python3 main.py
python3 main.py
python3 main.py
chmod 777 /home/opcc/app/server.py
sudo chmod 777 /home/opcc/app/server.py
ls -l /home/opcc/app/server.py
sudo chown -R opcc:opcc /home/opcc/app
ls -l /home/opcc/app/server.py
chmod 644 /home/opcc/app/server.py
python3 main.py
python3 main.py
/usr/bin/python3 /home/opcc/.vscode-server/extensions/ms-python.python-2025.10.1-linux-x64/python_files/printEnvVariablesToFile.py /home/opcc/.vscode-server/extensions/ms-python.python-2025.10.1-linux-x64/python_files/deactivate/bash/envVars.txt
python3 main.py
ls
python3 main.py
python3 main.py
clear
python3 main.py
cd app
ls
cd ..
cd OCPP_1.6_documentation/
ls
ls
python3 main.py
ls
git rm -r --cached .vscode-server/
git commit -m "Remove .vscode-server/ directory from tracking"
git commit -m "Remove .vscode-server/ directory from tracking"
git push origin master
pip install git-filter-repo
export PATH="/home/opcc/.local/bin:$PATH"
iwhich git-filter-repo
export PATH="/home/opcc/.local/bin:$PATH"
which git-filter-repo
git filter-repo --path .vscode-server/ --invert-paths
git filter-repo --path .vscode-server/ --invert-paths --force
git push --force origin master
git remote add origin git@github.com:SensorsIot/OCPP-Tester.git
git push --force origin master
git add .gitignore
git commit -m "Add .local/ to .gitignore"
git reflog expire --expire=now --all
git gc --prune=now
git reset HEAD~1
git rm -r --cached .local/
git add .gitignore
git commit -m "Add .local/ to .gitignore"
git push --force origin master
clear
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
python3 -m venv venv
source venv/bin/activate
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
sudo reboot now
python3 -m venv venv
source venv/bin/activate
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
ip a
sudo reboot now
pwd
python3 -m venv venv
source venv/bin/activate
python3 main.py 
python3 -m venv venv
source venv/bin/activate
python3 -m venv venv
source venv/bin/activate
python3 main.py 
clear
python3 main.py 
python3 -m venv venv
source venv/bin/activate
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
ip a
sudo reboot now
python3 -m venv venv
source venv/bin/activate
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
ls
cd app
ls
cd ..
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
clear
python3 main.py 
python3 -m venv venv
source venv/bin/activate
clear
python3 -m venv venv
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
python3 main.py 
