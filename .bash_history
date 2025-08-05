        elif message_type == MessageType.CALLERROR:
            return OCPPMessage(message_type, unique_id, error_code=data[2], 
                             error_description=data[3], payload=data[4])

    async def _handle_incoming_call(self, message: OCPPMessage):
        """Eingehende Calls von der Wallbox behandeln"""
        logger.info(f"Received {message.action}: {message.payload}")
        
        # Standard-Antworten für häufige Nachrichten
        response_payload = {}
        
        if message.action == OCPPAction.BOOT_NOTIFICATION.value:
            response_payload = {
                "currentTime": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "interval": 60,
                "status": "Accepted"
            }
        elif message.action == OCPPAction.STATUS_NOTIFICATION.value:
            response_payload = {}
        elif message.action == OCPPAction.METER_VALUES.value:
            response_payload = {}
        elif message.action == OCPPAction.HEARTBEAT.value:
            response_payload = {
                "currentTime": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            }
        
        # Antwort senden
        await self._send_call_result(message.unique_id, response_payload)

    async def _send_call_result(self, unique_id: str, payload: Dict):
        """CALLRESULT senden"""
        message = [MessageType.CALLRESULT.value, unique_id, payload]
        await self._send_message(message)

    async def _send_message(self, message: List):
        """Nachricht senden"""
        if not self.is_connected:
            raise Exception("Not connected")
        
        raw_message = json.dumps(message)
        logger.debug(f"Sending: {raw_message}")
        await self.websocket.send(raw_message)

    async def send_command(self, action: OCPPAction, payload: Dict, timeout: int = 30) -> Dict:
        """OCPP Command senden und auf Antwort warten"""
        unique_id = str(uuid.uuid4()).replace('-', '')[:10]  # Kurze ID wie im Log
        
        message = [MessageType.CALL.value, unique_id, action.value, payload]
        
        # Future für Antwort erstellen
        future = asyncio.Future()
        self.pending_requests[unique_id] = future
        
        try:
            await self._send_message(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            
            # Testergebnis speichern
            test_result = {
                "timestamp": datetime.now().isoformat(),
                "action": action.value,
                "payload": payload,
                "response": result,
                "success": True
            }
            self.test_results.append(test_result)
            
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(unique_id, None)
            logger.error(f"Timeout waiting for {action.value}")
            
            test_result = {
                "timestamp": datetime.now().isoformat(),
                "action": action.value,
                "payload": payload,
                "response": None,
                "success": False,
                "error": "Timeout"
            }
            self.test_results.append(test_result)
            raise
            
        except Exception as e:
            logger.error(f"Error in {action.value}: {e}")
            
            test_result = {
                "timestamp": datetime.now().isoformat(),
                "action": action.value,
                "payload": payload,
                "response": None,
                "success": False,
                "error": str(e)
            }
            self.test_results.append(test_result)
            raise

    # Test-Methoden basierend auf dem EVCC-Log
    async def test_change_availability(self, connector_id: int = 0, availability_type: str = "Operative"):
        """ChangeAvailability testen"""
        payload = {
            "connectorId": connector_id,
            "type": availability_type
        }
        return await self.send_command(OCPPAction.CHANGE_AVAILABILITY, payload)

    async def test_get_configuration(self, keys: Optional[List[str]] = None):
        """GetConfiguration testen"""
        payload = {}
        if keys:
            payload["key"] = keys
        return await self.send_command(OCPPAction.GET_CONFIGURATION, payload)

    async def test_change_configuration(self, key: str, value: str):
        """ChangeConfiguration testen"""
        payload = {
            "key": key,
            "value": value
        }
        return await self.send_command(OCPPAction.CHANGE_CONFIGURATION, payload)

    async def test_trigger_message(self, requested_message: str, connector_id: Optional[int] = None):
        """TriggerMessage testen"""
        payload = {
            "requestedMessage": requested_message
        }
        if connector_id is not None:
            payload["connectorId"] = connector_id
        return await self.send_command(OCPPAction.TRIGGER_MESSAGE, payload)

    async def test_get_composite_schedule(self, connector_id: int, duration: int):
        """GetCompositeSchedule testen"""
        payload = {
            "connectorId": connector_id,
            "duration": duration
        }
        return await self.send_command(OCPPAction.GET_COMPOSITE_SCHEDULE, payload)

    def get_test_results(self) -> List[Dict]:
        """Alle Testergebnisse zurückgeben"""
        return self.test_results

    def print_test_summary(self):
        """Test-Zusammenfassung ausgeben"""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result["success"])
        
        print(f"\n=== OCPP Test Summary ===")
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests}")
        print(f"Failed: {total_tests - successful_tests}")
        
        print(f"\n=== Test Details ===")
        for result in self.test_results:
            status = "✓" if result["success"] else "✗"
            print(f"{status} {result['action']}: {result.get('error', 'OK')}")


# Beispiel-Verwendung
async def main():
    tester = OCPPTester("TestWallbox001")
    
    try:
        # Zur Wallbox verbinden (URL anpassen)
        await tester.connect("ws://192.168.0.35:8887/")
        
        # Warten bis Verbindung steht
        await asyncio.sleep(2)
        
        print("Starting OCPP 1.6 Tests...")
        
        # Tests basierend auf EVCC-Log ausführen
        await tester.test_change_availability(0, "Operative")
        await tester.test_get_configuration()
        await tester.test_trigger_message("BootNotification")
        await tester.test_trigger_message("StatusNotification", 1)
        await tester.test_trigger_message("MeterValues", 1)
        
        # Konfiguration ändern (wie im Log)
        await tester.test_change_configuration("MeterValueSampleInterval", "10")
        
        # Composite Schedule testen (wird Fehler geben wie im Log)
        try:
            await tester.test_get_composite_schedule(1, 60)
        except Exception as e:
            print(f"Expected error: {e}")
        
        # Zusammenfassung
        tester.print_test_summary()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        await tester.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
EOF

# Virtuelle Umgebung sicherstellen
source venv/bin/activate
# Datei prüfen
head -5 ocpp_tester.py
# Sollte zeigen: #!/usr/bin/env python3
# Ausführen
python ocpp_tester.py
# Virtuelle Umgebung sicherstellen
source venv/bin/activate
# Datei prüfen
head -5 ocpp_tester.py
# Sollte zeigen: #!/usr/bin/env python3
# Ausführen
python ocpp_tester.py
source venv/bin/activate
cd ocpp-tester
source venv/bin/activate
python3 -m venv venv
source venv/bin/activate
python ocpp_tester.py
env) opcc@evcc:~/opcc-tester$ python ocpp_tester.py
Traceback (most recent call last):
  File "/home/opcc/opcc-tester/ocpp_tester.py", line 8, in <module>
    import websockets
ModuleNotFoundError: No module named 'websockets'
(venv) opcc@evcc:~/opcc-tester$
pip install websockets
pip install websockets
python ocpp_tester.py
ls
which
pwd
ls
git init
git add .
opcc@evcc:~$ git init
hint: Using 'master' as the name for the initial branch. This default branch name
hint: is subject to change. To configure the initial branch name to use in all
hint: of your new repositories, which will suppress this warning, call:
hint:
hint:   git config --global init.defaultBranch <name>
hint:
hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
hint: 'development'. The just-created branch can be renamed via this command:
hint:
hint:   git branch -m <name>
Initialized empty Git repository in /home/opcc/.git/
opcc@evcc:~$ git add .
fatal: detected dubious ownership in repository at '/home/opcc'
To add an exception for this directory, call:
        git config --global --add safe.directory /home/opcc
opcc@evcc:~$
sudo chown -R opcc:opcc /home/opcc
sudo chown -R opcc:opcc /home/opcc
git add .
git commit -m "Initial project setup"
opcc@evcc:~$ git commit -m "Initial project setup"
Author identity unknown
*** Please tell me who you are.
Run
  git config --global user.email "you@example.com"
  git config --global user.name "Your Name"
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
