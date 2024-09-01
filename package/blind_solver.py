import os
from math import floor


astap_path = "\"C:\\Program Files\\astap\\astap.exe\""
asi294_135mm_fov = 5.8
DEG_BY_H = 15.0
DEG_BY_DEC = 60.0
MINUTE_BY_DEC = 60.0
DEG_BY_M = DEG_BY_H / 60.0
DEG_BY_S = DEG_BY_M / 60.0
SEC_BY_DEC = 60.0 * MINUTE_BY_DEC


def degrees_to_declination(d):
    a = floor(d)
    d -= a
    m = floor(d*MINUTE_BY_DEC)
    d -= m / MINUTE_BY_DEC
    s = d * SEC_BY_DEC
    return a, m, s


def degrees_to_right_ascension(d):
    h = floor(d / DEG_BY_H)
    d -= h*DEG_BY_H
    m = floor(d / DEG_BY_M)
    d -= m*DEG_BY_M
    s = d / DEG_BY_S
    return h, m, s


def blind_solve_image(file_name, ra, dec):
    print(f"Trying to solve {file_name}")
    cmd_args = f" -f {file_name} -r 30 -fov {asi294_135mm_fov} -ra {ra} -dec {dec} -m 1.5 -D D20"
    print(f"Calling {cmd_args}")
    os.system(astap_path + cmd_args)
    root_name = os.path.splitext(file_name)[0]
    print(f"Opening {root_name}.ini")
    try:
        with open(f"{root_name}.ini", 'r') as f:
            dictionable_lines = [line.split("=") for line in f.readlines()[:-1] if "=" in line]
    except Exception as e:
        print(f"Exception caught: {e}")
        return (0,0,0), (0,0,0)
    print(f"Read ini file!")
    dictionary = {split_line[0].strip(): split_line[1].strip() for split_line in dictionable_lines}
    ra_deg = float(dictionary["CRVAL1"])
    h,m,s = degrees_to_right_ascension(ra_deg)
    dec_deg = float(dictionary["CRVAL2"])
    da, dm, ds = degrees_to_declination(dec_deg)
    print(f"Ra = {h}:{m}:{s}, Dec = {da}:{dm}:{ds}")
    return (h,m,s),(da,dm,ds)