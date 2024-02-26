# League Proximity Chat Spike
# Initial Goals:
# 1. Retrieve client credential
# 2. Access the league client's API
# 3. Be able to determine when a client is in game
# 4. Be able to get every player's positions (where reasonable)
#
# From there, we will have the basic process and can look to improve or work it into
# something else.

import os
import psutil
from dataclasses import dataclass
import requests
import base64
from urllib3.exceptions import InsecureRequestWarning

# === Step 1: Retrieve client credentials === #
# 1A. Determine install location of League of Legends
# There's a lockfile the application creates when the user has signed into the client
# that contains information about how to access the API

def find_league_client_lockfile():
    # Start by looking for running League Client, as we need it running for
    # the lockfile anyway
    try:
        exe_location = [process.exe() for process in psutil.process_iter() if "leagueclient.exe" in process.name().lower()][0]
    except IndexError:
        raise RuntimeError("No process found for League Client")
    return os.path.join(os.path.dirname(exe_location), "lockfile")

# According to https://hextechdocs.dev/getting-started-with-the-lcu-api/ you can
# also parse it from the command arguments, so here's a function to do that
# so I don't forget it exists
def get_league_api_from_process():
    # NOTE: the ui disappears when in game now, so this won't work if the
    # user is already in game
    # Start by looking for running League Client
    try:
        lol_proc = [process for process in psutil.process_iter() if "leagueclientux.exe" in process.name().lower()][0]
    except IndexError:
        raise RuntimeError("No process found for League Client UI")
    # Torture the computer for an argument list in one line
    proc_args = {arg.split('=')[0]:arg.split('=')[1] if len(arg.split('=')) > 1 else None for arg in lol_proc.cmdline()}
    return LockfileContents(lol_proc.name(), lol_proc.pid, proc_args["--app-port"], proc_args["--remoting-auth-token"], "https")

# 2A. Parse lockfile
# Dataclass "struct" for lockfile properties
@dataclass
class LockfileContents:
    process_name: str
    process_id: int
    api_port: int
    api_password: str
    api_protocol: str

def parse_league_lockfile(lockfile_path):
    with open(lockfile_path) as lockfile:
        return LockfileContents(*lockfile.read().split(':'))

# === Step 2: Verify we can connect to the league client API
# 2A. Construct authorization header
def construct_basic_auth(api_password):
    # LCU API uses Basic Auth
    # Username is "riot"
    basic_login = f"riot:{api_password}"
    return base64.standard_b64encode(bytes(basic_login, 'utf-8')).decode('utf-8')

# 2B. Get the current user as a test
def get_current_user(basic_auth, api_port, api_protocol="https"):
    # Tiny potential pitfall, localhost will receive a 403, 127.0.0.1 works
    endpoint = f"{api_protocol}://127.0.0.1:{api_port}/lol-summoner/v1/current-summoner"

    # Hextech docs have the root cert @ https://static.developer.riotgames.com/docs/lol/riotgames.pem
    # Ignore if we don't have it, use it if we do
    should_verify = "riotgames.pem" if os.path.exists("riotgames.pem") else False
    resp = requests.get(endpoint, verify=should_verify, headers={"Authorization": f"Basic {basic_auth}"})
    if resp.status_code != 200:
        raise RuntimeError(f"LCU API returned non-200 status code {resp.status_code}")

    # Keep it simple and return display name and tag
    resp = resp.json()
    return f"{resp['displayName']}#{resp['tagLine']}"

# === Step 3: Be able to check if a user is in game
def is_user_in_game(basic_auth, api_port, api_protocol="https"):
    endpoint = f"{api_protocol}://127.0.0.1:{api_port}/lol-gameflow/v1/gameflow-phase"
    should_verify = "riotgames.pem" if os.path.exists("riotgames.pem") else False
    resp = requests.get(endpoint, verify=should_verify, headers={"Authorization": f"Basic {basic_auth}"})
    if resp.status_code != 200:
        raise RuntimeError(f"LCU API returned non-200 status code {resp.status_code}")

    return resp.text == '"InProgress"'

# === Step 4: Get player positions
# 4A. UI is one game client, but the actual game uses a different live game client
# Connect to the actual live game client, hardcoded at 2999, and get the active player to test
# NOTE: Since the live game client doesn't seem to need auth, steps 1-3 may not be relevant for
# the purposes of proximity chat
def get_ingame_user(api_protocol="https"):
    endpoint = f"{api_protocol}://127.0.0.1:2999/liveclientdata/activeplayername"
    should_verify = "riotgames.pem" if os.path.exists("riotgames.pem") else False
    resp = requests.get(endpoint, verify=should_verify)
    if resp.status_code != 200:
        raise RuntimeError(f"LCU API returned non-200 status code {resp.status_code}")

    return resp.text.strip('"')

# 4B. Get player positions
# NOTE: This is not natively supported by the live client? My initial thoughts here
# were that you would only be able to see positions the server sent
# back, so as to prevent cheating, so we could assume anyone without
# a position is not visible and should not be heard.
# May need to look into an alternative, but at least this file
# outlines the high level of working with the LCU & Live Client
# APIs.

# === Testing what's here === #
# This runs immediately, and does not enter a loop, so
# use the lockfile method in case user is in game.
try:
    lc = parse_league_lockfile(find_league_client_lockfile())
except RuntimeError:
    print("League client lockfile not detected")
    exit(1)
print(lc)

basic_auth = construct_basic_auth(lc.api_password)
user = get_current_user(basic_auth, lc.api_port, lc.api_protocol)
print(f"Username: {user}")

in_game = is_user_in_game(basic_auth, lc.api_port, lc.api_protocol)
print("In Game" if in_game else "Not In Game")
if in_game:
    print(f"In Game As: {get_ingame_user()}")