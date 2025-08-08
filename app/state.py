"""
This module defines the in-memory state management for the OCPP server.
It holds dictionaries to track connected charge points and their transactions.
"""

# A simple in-memory dictionary to store the state of each charge point.
CHARGE_POINTS = {}

# A simple in-memory dictionary to store active and past transactions.
TRANSACTIONS = {}