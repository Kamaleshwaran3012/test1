import os

def run_container():
    os.system("docker build -t surgeon-test .")
    os.system("docker run surgeon-test")