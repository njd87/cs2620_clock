import socket
import threading
import random
import time
import queue
import sys
import json
import concurrent.futures

# load config file
config = json.load(open('config/config.json'))

# set params from config
host = config['host']
ports = [config['port1'], config['port2'], config['port3']]
run_duration = config['run_duration']
max_internal = config['max_internal']
max_clock_speed = config['max_clock_speed']

class VirtualMachine:
    def __init__(self, machine_id, port, peers, host, max_clock_speed, max_internal):
        '''
        Class that runs a virtual machine that can send and receive messages.
        Sets clock speed at initialization and logs info.

        Parameters:
        ----------
        machine_id : int
            The unique identifier for this machine.
        port : int
            The port number to listen on for incoming connections.
        peers : list of tuples
            Each tuple contains (peer_id, host, port) for each peer.
        host : str
            Hostname for binding the socket.
        max_clock_speed : int
            Maximum possible clock speed.
        max_internal : int
            Maximum value used when deciding between actions.
        '''
        self.machine_id = machine_id
        self.port = port
        self.peers = peers
        self.host = host
        self.max_clock_speed = max_clock_speed
        self.max_internal = max_internal

        # this maps peer_id to a socket object
        self.peer_sockets = {}

        # get random clock speed
        self.clock_speed = random.randint(1, self.max_clock_speed)

        # initialize logical clock and inbound message queue
        self.logical_clock = 0
        self.inbound_queue = queue.Queue()

        # create log file
        self.log_file = f"logs/machine_{self.machine_id}_log.txt"
        with open(self.log_file, "w") as f:
            f.write(f"Max internal event={self.max_internal}\n")
            f.write(f"Max clock speed={self.max_clock_speed}\n")
            f.write(f"Machine {self.machine_id} initialized. Clock rate={self.clock_speed}\n")

        # set up listening socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)

        # start connection listener in a dedicated thread
        self.connection_thread = threading.Thread(target=self.setup_connection, daemon=True)
        self.connection_thread.start()

    def setup_connection(self):
        '''
        Continuously listens for incoming connections.
        '''
        while True:
            conn, _ = self.socket.accept()
            threading.Thread(target=self.handle_requests, args=(conn,), daemon=True).start()

    def handle_requests(self, conn):
        '''
        Handles incoming requests from peers.
        '''
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                message_str = data.decode('utf-8').strip()
                if message_str:
                    parts = message_str.split(":")
                    sender_id = int(parts[0])
                    sender_clock = int(parts[1])
                    self.inbound_queue.put((sender_id, sender_clock))
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"[Machine {self.machine_id}] Error in handle_requests: {e}", file=sys.stderr)
                break
        conn.close()

    def connect_to_peers(self):
        '''
        Creates and stores socket connections to all peers.
        '''
        for (peer_id, peer_host, peer_port) in self.peers:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connected = False
            while not connected:
                try:
                    s.connect((peer_host, peer_port))
                    connected = True
                except ConnectionRefusedError:
                    time.sleep(0.1)
            self.peer_sockets[peer_id] = s

    def _log_event(self, event_type, extra_info=""):
        '''
        Appends an event to the machine's log file.
        '''
        system_time = time.time()
        log_line = (f"[{event_type}] SystemTime={system_time:.4f}, "
                    f"LogicalClock={self.logical_clock}, Info={extra_info}\n")
        with open(self.log_file, "a") as f:
            f.write(log_line)

    def update_logical_clock_on_receive(self, sender_clock):
        '''
        Update the local logical clock on receiving a message.
        '''
        self.logical_clock = max(self.logical_clock, sender_clock) + 1

    def increment_clock(self):
        '''
        Increment the logical clock.
        '''
        self.logical_clock += 1

    def send_message(self, peer_id):
        '''
        Sends a message "machine_id:logical_clock" to a peer.
        '''
        if peer_id not in self.peer_sockets:
            return
        msg = f"{self.machine_id}:{self.logical_clock}\n".encode('utf-8')
        try:
            self.peer_sockets[peer_id].sendall(msg)
        except OSError as e:
            print(f"[Machine {self.machine_id}] Failed to send to {peer_id}: {e}", file=sys.stderr)

    def main_loop(self, run_duration, force_test=None):
        '''
        Simulates the instruction cycle for this machine.
        Runs for run_duration seconds.
        '''
        start_time = time.time()
        while True:
            sleep_time = 1.0 / self.clock_speed

            # process one inbound message if available
            if not self.inbound_queue.empty():
                sender_id, sender_clock = self.inbound_queue.get()
                old_clock = self.logical_clock
                self.update_logical_clock_on_receive(sender_clock)
                queue_size = self.inbound_queue.qsize()
                self._log_event("RECEIVE", (f"From={sender_id}, SenderClock={sender_clock}, "
                                             f"QueueSizeAfter={queue_size}, OldLocalClock={old_clock}"))
            else:
                choice = random.randint(1, self.max_internal)
                if force_test:
                    choice = force_test
                if choice == 1:
                    if self.peer_sockets:
                        peer_id = list(self.peer_sockets.keys())[0]
                        self.send_message(peer_id)
                        self.increment_clock()
                        self._log_event("SEND", f"To={peer_id}")
                elif choice == 2:
                    if len(self.peer_sockets) > 1:
                        peer_id = list(self.peer_sockets.keys())[1]
                        self.send_message(peer_id)
                        self.increment_clock()
                        self._log_event("SEND", f"To={peer_id}")
                    else:
                        self.increment_clock()
                        self._log_event("INTERNAL", "Random=2 but only one peer.")
                elif choice == 3:
                    for peer_id in self.peer_sockets:
                        self.send_message(peer_id)
                    self.increment_clock()
                    self._log_event("SEND", f"Broadcast to peers {list(self.peer_sockets.keys())}")
                else:
                    old_clock = self.logical_clock
                    self.increment_clock()
                    self._log_event("INTERNAL", f"old_clock={old_clock}")

            if time.time() - start_time >= run_duration:
                break
            time.sleep(sleep_time)

def run_vm(machine_id, port, peers, host, run_duration, max_clock_speed, max_internal):
    vm = VirtualMachine(machine_id, port, peers, host, max_clock_speed, max_internal)
    # wait a moment to let all machines listen before connecting
    time.sleep(0.5)
    vm.connect_to_peers()
    vm.main_loop(run_duration)
    return f"Machine {machine_id} finished."

def main():
    # prepare peer info for each machine
    all_machines = []
    for i in range(3):
        machine_id = i + 1
        listen_port = ports[i]
        peer_info = []
        for j in range(3):
            if j != i:
                peer_info.append((j + 1, host, ports[j]))
        all_machines.append((machine_id, listen_port, peer_info))

    print(f"System running for {run_duration} seconds...")

    with concurrent.futures.ProcessPoolExecutor(max_workers=3) as executor:
        futures = []
        for machine_id, listen_port, peer_info in all_machines:
            future = executor.submit(run_vm, machine_id, listen_port, peer_info,
                                     host, run_duration, max_clock_speed, max_internal)
            futures.append(future)

        # wait for each machine's process to finish
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                print(result)
            except Exception as exc:
                print(f"Machine generated an exception: {exc}", file=sys.stderr)

    print("Done.")

if __name__ == "__main__":
    main()
