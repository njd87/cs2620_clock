import time
import unittest
import socket
import os

from main import VirtualMachine

unittest.TestLoader.sortTestMethodsUsing = None

class TestConnections(unittest.TestCase):
    '''
    Tests connections between virtual machines

    Checks to make sure that the connections between virtual machines are established
    and messages can be sent.
    '''
    @classmethod
    def setUpClass(cls):
        # setup vms with 2 peers (3 machines total)
        cls.machines = []
        ports = [5001, 5002, 5003]
        for i in range(3):
            machine_id = i + 1
            listen_port = ports[i]
            peer_info = []
            for j in range(3):
                if j != i:
                    peer_info.append((j+1, "localhost", ports[j]))
            vm = VirtualMachine(machine_id, listen_port, peer_info)
            cls.machines.append(vm)

        # connect to peers
        for vm in cls.machines:
            vm.connect_to_peers()
    
    @classmethod
    def tearDownClass(cls):
        # close all sockets
        for vm in cls.machines:
            for peer_socket in vm.peer_sockets.values():
                peer_socket.close()

    def test1a_connections_exist(self):
        # make sure each vm has a length of 2 dictionary in peer_sockets
        for vm in self.machines:
            self.assertEqual(len(vm.peer_sockets), 2)

    def test1b_connections_are_sockets(self):
        # make sure each vm has a socket in peer_sockets
        for vm in self.machines:
            for peer_socket in vm.peer_sockets.values():
                self.assertIsInstance(peer_socket, socket.socket)
    
    def test1c_send_message(self):
        # send message from first vm to second vm
        self.machines[0].send_message(2)

        # sleep for a bit to allow message to be received
        time.sleep(0.5)

        if not self.machines[1].inbound_queue.empty():
            s = self.machines[1].inbound_queue.get()
            self.assertEqual(s, (1, 0))

    def test1d_send_all_messages(self):
        # send message from second vm to both first and third vm
        self.machines[1].send_message(1)
        self.machines[1].send_message(3)

        # sleep for a bit to allow message to be received
        time.sleep(0.5)

        # check first vm
        if not self.machines[0].inbound_queue.empty():
            s = self.machines[0].inbound_queue.get()
            self.assertEqual(s, (2, 0))

        # check third vm
        if not self.machines[2].inbound_queue.empty():
            s = self.machines[2].inbound_queue.get()
            self.assertEqual(s, (2, 0))

class TestMainLoop(unittest.TestCase):
    '''
    Test to make sure main loop is working correctly.

    Check logic clocks, sending etc.
    '''
    @classmethod
    def setUpClass(cls):
        # setup vms with 2 peers (3 machines total)
        cls.machines = []
        ports = [5004, 5005, 5006]
        for i in range(3):
            machine_id = i + 1
            listen_port = ports[i]
            peer_info = []
            for j in range(3):
                if j != i:
                    peer_info.append((j+1, "localhost", ports[j]))
            vm = VirtualMachine(machine_id, listen_port, peer_info)
            cls.machines.append(vm)

        # connect to peers
        for vm in cls.machines:
            vm.connect_to_peers()
    
    @classmethod
    def tearDownClass(cls):
        # close all sockets
        for vm in cls.machines:
            for peer_socket in vm.peer_sockets.values():
                peer_socket.close()

    def test1a_test_randint_1(self):
        # run main loop on vm1, sending message to vm2
        self.machines[0].main_loop(6)
        self.machines[0].main_loop(1)
        time.sleep(0.5)

        # check vm2
        self.machines[1].main_loop(4)

        self.machines[2].main_loop(4)

        # vm1 logic clock should be 2 [2 events]
        # vm2 logic clock should be 2 [received 1 from vm1, + 1]
        # vm3 logic clock should be 1 [only did one thing]

        self.assertEqual(self.machines[0].logical_clock, 2)
        self.assertEqual(self.machines[1].logical_clock, 2)
        self.assertEqual(self.machines[2].logical_clock, 1)

    def test1b_test_randint_2(self):
        # test randint 2, which sends message to second vm peer
        self.machines[0].main_loop(4)
        self.machines[0].main_loop(2)
        time.sleep(0.5)

        # check vm2
        self.machines[1].main_loop(5)

        self.machines[2].main_loop(5)

        # vm1 logic clock should be 4 [4 events]
        # vm2 logic clock should be 3 [received 1 from vm1, + 1, now 1 new event]
        # vm3 logic clock should be 4 [received from vm1]

        self.assertEqual(self.machines[0].logical_clock, 4)
        self.assertEqual(self.machines[1].logical_clock, 3)
        self.assertEqual(self.machines[2].logical_clock, 4)

    def test1c_test_randint_3(self):
        # test randint 2, which sends message to second vm peer
        self.machines[0].main_loop(4)
        self.machines[0].main_loop(4)
        self.machines[0].main_loop(4)
        self.machines[0].main_loop(3)
        time.sleep(0.5)

        self.machines[1].main_loop(5)
        self.machines[2].main_loop(5)

        # vm1 logic clock should be 8
        # vm2 logic clock should be 8
        # vm3 logic clock should be 8

        self.assertEqual(self.machines[0].logical_clock, 8)
        self.assertEqual(self.machines[1].logical_clock, 8)
        self.assertEqual(self.machines[2].logical_clock, 8)

    def test1d_test_internal(self):
        # test randint 2, which sends message to second vm peer
        self.machines[0].main_loop(4)
        self.machines[0].main_loop(5)
        self.machines[0].main_loop(6)
        self.machines[0].main_loop(7)
        self.machines[0].main_loop(8)
        self.machines[0].main_loop(9)
        self.machines[0].main_loop(10)
        time.sleep(0.5)

        self.machines[1].main_loop(5)

        time.sleep(0.5)

        # vm1 logic clock should be 15, 7 new internal events
        # vm2 logic clock should be 9, 1 new internal event
        # vm3 logic clock should be 8, 0 new internal events

        self.assertEqual(self.machines[0].logical_clock, 15)
        self.assertEqual(self.machines[1].logical_clock, 9)
        self.assertEqual(self.machines[2].logical_clock, 8)


if __name__ == "__main__":
    unittest.main()