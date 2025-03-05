# What is this project

This project is made for Harvard's Compsci 2620 course on distributed system. The repo is meant to simulate 3 virtual machines running on randomized clock speeds communicating with each other over sockets, attempting to syncrhonize time over asyncrhonous operations.

# How to run
Simply run

```bash
python3 main.py
```

or

```bash
python main.py
```

Depending on how the python path is set up in your command line.

Running will create or append to the 3 log files (if already created) the clock speed and whenever the machine receives, sends, or does an internal operation, printing out its logical clock time and what it receives/updates to.

# Changing Config

If you would like to change the port, host, or time that the program runs for (defaults are listed in config, run_duration in seconds), change to your desired params in config/config.json.

You may also change the maximum clock rate possible (default 6) and maximum number of events. 1-3 reserved for sending. Param requires minimum of 4, default 10.