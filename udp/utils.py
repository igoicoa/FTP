import pickle
import os


def assembly_packet(packet):
    return pickle.dumps(packet)


def extract_packet(packet):
    return pickle.loads(packet)


def create_file(filename):
    new_file = open(filename, "w")
    new_file.close()


def write_into_file(filename, data):
    # print("filename: ", filename)
    file = open(filename, 'a')
    # print("data: ", data)
    file.write(data)
    file.close()


def file_exists(source_dir, filename):
    return os.path.isfile(f"{source_dir}/{filename}")


def format_address(addr):
    return f"{addr[0]}:{addr[1]}"
