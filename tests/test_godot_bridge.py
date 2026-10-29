"""Real loopback protocol checks; never opens serial or launches Godot."""
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
from device_studio.godot_bridge import GodotBridge, MAX_LINE, find_godot


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.bridge = GodotBridge(clock=lambda: self.now, token='unit-secret')
        self.peers = []
    def tearDown(self):
        for peer in self.peers:
            peer.close()
        self.bridge.close()
    def peer(self):
        peer = socket.create_connection(('127.0.0.1', self.bridge.port), timeout=.2)
        peer.settimeout(.2)
        self.peers.append(peer)
        for _ in range(10):
            self.bridge.poll()
            time.sleep(.001)
        return peer
    def network_events(self):
        deadline=time.monotonic()+.25
        while time.monotonic()<deadline:
            events=self.bridge.poll()
            if events or self.bridge.peer is None:return events
            time.sleep(.001)
        return []
    def send(self, peer, message):
        peer.sendall(json.dumps(message).encode()+b'\n')
        return self.network_events()
    def authenticate(self):
        peer = self.peer()
        events = self.send(peer, dict(type='hello',protocol=1,token=self.bridge.token))
        self.assertEqual(events,[dict(type='connected')])
        return peer
    def test_fragmented_hello_is_not_authenticated_before_newline(self):
        peer=self.peer()
        wire=json.dumps(dict(type='hello',protocol=1,token=self.bridge.token)).encode()
        peer.sendall(wire[:12]);self.assertEqual(self.bridge.poll(),[])
        self.assertFalse(self.bridge.connected)
        peer.sendall(wire[12:]+b'\n')
        self.assertEqual(self.network_events(),[dict(type='connected')])
        self.assertFalse(self.bridge.active)
    def test_wrong_token_does_not_claim_renderer_and_next_peer_can_authenticate(self):
        peer=self.peer();self.send(peer,dict(type='hello',protocol=1,token='wrong'))
        self.assertFalse(self.bridge.connected);self.assertIsNone(self.bridge.peer)
        self.authenticate();self.assertTrue(self.bridge.connected)
    def test_boolean_protocol_does_not_alias_integer_protocol_one(self):
        peer=self.peer();self.send(peer,dict(type='hello',protocol=True,token=self.bridge.token))
        self.assertFalse(self.bridge.connected);self.assertIsNone(self.bridge.peer)
    def test_authenticated_commands_and_focus_heartbeat_are_forwarded(self):
        peer=self.authenticate()
        messages=[dict(type='heartbeat',active=True),dict(type='input',key='w',pressed=True,repeat=False),
                  dict(type='setting',key='mode',value='warn'),dict(type='action',name='start')]
        peer.sendall(b''.join(json.dumps(m).encode()+b'\n' for m in messages))
        self.assertEqual(self.network_events(),messages);self.assertTrue(self.bridge.active)
    def test_malformed_batch_discards_prior_input_and_disconnects(self):
        peer=self.authenticate()
        peer.sendall(b'{"type":"action","name":"start"}\n{bad json}\n')
        events=self.network_events()
        self.assertEqual([e['type'] for e in events],['disconnected'])
        self.assertFalse(self.bridge.connected)
    def test_stale_heartbeat_disconnects_even_when_key_messages_arrive(self):
        peer=self.authenticate();self.send(peer,dict(type='heartbeat',active=True))
        self.now += .351
        events=self.send(peer,dict(type='input',key='w',pressed=True))
        self.assertEqual(events,[dict(type='disconnected',reason='heartbeat_timeout')])
        self.assertFalse(self.bridge.active)
    def test_authentication_deadline_frees_slot(self):
        self.peer();self.now += 3.01;self.bridge.poll()
        self.assertIsNone(self.bridge.peer)
        self.authenticate()
    def test_second_client_cannot_replace_authenticated_renderer(self):
        first=self.authenticate();second=self.peer()
        self.assertEqual(second.recv(1),b'')
        self.assertTrue(self.bridge.connected)
        self.assertEqual(self.send(first,dict(type='heartbeat',active=True)),[dict(type='heartbeat',active=True)])
    def test_oversized_partial_line_cannot_accumulate_unbounded_memory(self):
        peer=self.authenticate();peer.sendall(b'x'*(MAX_LINE+1))
        events=self.network_events()
        self.assertFalse(self.bridge.connected)
        self.assertEqual(len(self.bridge._input),0)
        self.assertEqual(events[-1]['type'],'disconnected')
    def test_command_flood_is_bounded_and_not_applied(self):
        peer=self.authenticate()
        peer.sendall(b'{"type":"action","name":"start"}\n'*65)
        events=self.network_events()
        self.assertEqual([e['type'] for e in events],['disconnected'])
    def test_strict_input_and_setting_types_disconnect_bad_peer(self):
        for message in [dict(type='input',key='w',pressed=1),dict(type='setting',key='targetKmh',value=True),
                        dict(type='setting',key='mode',value='unknown')]:
            peer=self.authenticate();events=self.send(peer,message)
            self.assertEqual(events[-1]['type'],'disconnected')
    def test_only_newest_complete_state_is_queued(self):
        peer=self.authenticate()
        for n in range(20):self.bridge.send_state(dict(sequence=n),connected=True,backend='ARM_SIM')
        self.bridge.poll()
        result=json.loads(peer.recv(MAX_LINE))
        self.assertEqual(result['state']['sequence'],19)
        self.assertEqual(result['backend'],'ARM_SIM')
        self.assertEqual(result['protocol'],1)
    def test_deeply_nested_malformed_json_does_not_escape_poll(self):
        peer=self.authenticate()
        peer.sendall(b'['*1500+b'0'+b']'*1500+b'\n')
        events=self.network_events()
        self.assertEqual(events[-1]['type'],'disconnected')
        self.assertFalse(self.bridge.connected)
    def test_nonfinite_or_oversized_state_is_rejected(self):
        self.authenticate()
        with self.assertRaises(ValueError):self.bridge.send_state(dict(a=float('nan')),connected=True,backend='ARM_SIM')
        with self.assertRaises(ValueError):self.bridge.send_state(dict(a='x'*MAX_LINE),connected=True,backend='ARM_SIM')
    def test_explicit_engine_path_and_missing_override(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'engine with spaces';executable.write_text('#!/bin/sh\n');executable.chmod(0o755)
            with patch.dict(os.environ,{'GODOT_BIN':str(executable)}):self.assertEqual(find_godot(folder),executable)
            with patch.dict(os.environ,{'GODOT_BIN':str(executable)+'-missing'}):self.assertIsNone(find_godot(folder))
