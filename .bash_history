# Sollte zeigen: /home/opcc/ocpp-tester
ls -la
# Zeigt alle Dateien im Verzeichnis
cc@evcc:/home$ ls
opcc@evcc:/home$ ^C
opcc@evcc:/home$ pwd
# Sollte zeigen: /home/opcc/ocpp-tester
ls -la
# Zeigt alle Dateien im Verzeichnis
/home
total 8
drwxr-xr-x  2 root root 4096 Aug  3 21:56 .
drwxr-xr-x 18 root root 4096 Aug  2 21:34 ..
opcc@evcc:/home$
ls
ls
cd opcc/
cd opcc-tester/
cat > ocpp_tester.py << 'EOF'
#!/usr/bin/env python3
"""
OCPP 1.6 Tester für Wallboxen
Basierend auf dem EVCC-Log Trace
"""

import asyncio
import websockets
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Logging Setup
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(levelname)s %(asctime)s %(message)s')
logger = logging.getLogger('ocpp_tester')

class MessageType(Enum):
    CALL = 2
    CALLRESULT = 3
    CALLERROR = 4

class OCPPAction(Enum):
    # Core Profile
    BOOT_NOTIFICATION = "BootNotification"
    STATUS_NOTIFICATION = "StatusNotification"
    GET_CONFIGURATION = "GetConfiguration"
    CHANGE_CONFIGURATION = "ChangeConfiguration"
    CHANGE_AVAILABILITY = "ChangeAvailability"
    TRIGGER_MESSAGE = "TriggerMessage"
    METER_VALUES = "MeterValues"
    HEARTBEAT = "Heartbeat"
    
    # Smart Charging Profile
    GET_COMPOSITE_SCHEDULE = "GetCompositeSchedule"
    SET_CHARGING_PROFILE = "SetChargingProfile"
    CLEAR_CHARGING_PROFILE = "ClearChargingProfile"

@dataclass
class OCPPMessage:
    message_type: MessageType
    unique_id: str
    action: Optional[str] = None
    payload: Dict = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None

class OCPPTester:
    def __init__(self, charge_point_id: str = "TestChargePoint"):
        self.charge_point_id = charge_point_id
        self.websocket = None
        self.is_connected = False
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.test_results: List[Dict] = []
        
    async def connect(self, url: str):
        """Verbindung zur Wallbox aufbauen"""
        try:
            logger.info(f"Connecting to {url}")
            self.websocket = await websockets.connect(url)
            self.is_connected = True
            logger.info("Connected successfully")
            
            # Message Handler starten
            asyncio.create_task(self._message_handler())
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def disconnect(self):
        """Verbindung trennen"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
            logger.info("Disconnected")

    async def _message_handler(self):
        """Eingehende Nachrichten verarbeiten"""
        try:
            async for raw_message in self.websocket:
                logger.debug(f"Received: {raw_message}")
                
                try:
                    message_data = json.loads(raw_message)
                    message = self._parse_message(message_data)
                    
                    if message.message_type == MessageType.CALLRESULT:
                        # Antwort auf unsere Anfrage
                        if message.unique_id in self.pending_requests:
                            future = self.pending_requests.pop(message.unique_id)
                            future.set_result(message.payload)
                    
                    elif message.message_type == MessageType.CALLERROR:
                        # Fehlerantwort
                        if message.unique_id in self.pending_requests:
                            future = self.pending_requests.pop(message.unique_id)
                            future.set_exception(Exception(f"{message.error_code}: {message.error_description}"))
                    
                    elif message.message_type == MessageType.CALL:
                        # Eingehende Anfrage von der Wallbox
                        await self._handle_incoming_call(message)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed")
            self.is_connected = False

    def _parse_message(self, data: List) -> OCPPMessage:
        """OCPP Message parsen"""
        message_type = MessageType(data[0])
        unique_id = data[1]
        
        if message_type == MessageType.CALL:
            return OCPPMessage(message_type, unique_id, data[2], data[3])
        elif message_type == MessageType.CALLRESULT:
            return OCPPMessage(message_type, unique_id, payload=data[2])
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
