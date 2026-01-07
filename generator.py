### = Annotation for section of code
## = Todo
# = General annotations, explains pieces of code.

import os
import sys, getopt
import configparser
import datetime
from operator import attrgetter

### Handle command line options/arguments
args = sys.argv[1:]
short_options = "tnfrc:"
long_options = ["sort-by-title", "sort-by-number", "sort-by-filename", "reverse", "config="]
try:
    arguments, trailing = getopt.getopt(args, short_options, long_options)
except getopt.GetoptError as err:
    print(err)
    sys.exit(2)

config = "config.ini"
config_path = os.path.abspath(config)

reverse_mode = True
file_mode = False
number_mode = False
title_mode = False
for option, value in arguments:
    if option in ("-c", "--config"):
        config = os.path.expanduser(value)
    elif option in ("-t", "--sort-by-title"):
        title_mode = True
    elif option in ("-n", "--sort-by-number"):
        number_mode = True
    elif option in ("-r", "--reverse"):
        # The value of reverse_mode will be passed into the sort() method's reverse= parameter. Although it may seem counterintuitive, reverse_mode *disables* sort's reverse feature. This is because the default behavior should generate a blog with posts from newest to oldest, which would require the sort() reverse= paramater to be True.
        reverse_mode = False
    elif option in ("-f", "--sort-by-filename"):
        file_mode = True


config = os.path.abspath(config)

### Import values from config file. 
if not os.path.isfile(config):
    print("Config file does not exist. Ensure that the config file, config.ini, is located in the same directory as the generator script. Alternatively, specify the path of the config file using the command line option: --config=[path/to/config] or -c [path/to/config]")
    sys.exit(2)

iniparser = configparser.ConfigParser()
iniparser.read(config)

# Check if the config file is written correctly
def validate_config(config, section, keys):
    for key in keys:
        if not iniparser.has_option(section, key):
            print(f"The option {key} is missing from the config file: {config_path}")
## Add link to documentation here
            print(f"For information on how to set up and write the config file, please see the documentation at: [link to documentation]")
            sys.exit(2)

validate_config(config, 'Paths', ['OutputDirectory', 'SourceDirectory', 'PageTemplate', 'PostTemplate'])

# Check if paths specified in config file point to existing files and directories.
def validate_path(config, section, key, item_name, is_directory):
    path = os.path.expanduser(iniparser[section][key])
    exists = os.path.isdir(path) if is_directory else os.path.isfile(path)
    if exists:
        # Paths are saved as absolute. This may come at some cost to memory when later on when saving a list of file paths to source_files. However, the concreteness that is gained from using absolute paths may be worth the increased memory size, especially on modern computers.
        path = os.path.abspath(path)
        return path
    else:
        print(f"Could not find the {item_name} at: {path}")
        print(f"Config file in which the location of the {item_name} was specified: {config_path}")
        print(f"Please ensure that the location specified in the config file represents the true location of the {item_name}.")
        sys.exit(2)

output_dir = validate_path(config, 'Paths', 'OutputDirectory', "output directory", is_directory=True)
source_dir = validate_path(config, 'Paths', 'SourceDirectory', "source directory", is_directory=True)
page_template = validate_path(config, 'Paths', 'PageTemplate', "page template", is_directory=False)
post_template = validate_path(config, 'Paths', 'PostTemplate', "post template", is_directory=False)

### Create objects for blog posts located in source_dir
### Source files will be parsed for metadata and body text, which will then be saved in object properties
post_objects = list()
class BlogPost:
    def __init__(self, filename, title, date, categories, number, body):
        self.filename = filename
        self.title = title
        self.date = date
        self.categories = categories
        self.number = number
        self.body = body

# Traverse the source_dir recursively and save files to source_files list
# Symlinks are not followed to prevent an error where os.walk enters an infinite loop
source_files = list()
for rootdir, dirnames, filenames in os.walk(source_dir, topdown=True, followlinks=False):
    for file in filenames:
        if file.endswith('.swp'):
            continue
        file_path = os.path.join(rootdir, file)
        source_files.append(file_path)

# Function for pulling metadata out of a source file and saving it to a dict
data = dict()
def get_value(line, file_key, dict_key):
    if line.startswith(file_key):
        data[dict_key] = line.removeprefix(file_key)
        data[dict_key] = data[dict_key].removesuffix('\n')
        if file_key == "C=":
            data[dict_key] = data[dict_key].split(",")
        elif file_key == "DATE=":
            data[dict_key] = data[dict_key].split(" ")

# Go through source file line by line. If metadata is encountered, parse it and save it to a dict. Parse body text.
in_body = False
for file in source_files:
    if os.path.getsize(file) == 0:
        continue
    f = open(file, "r")
    for l in f:
        if l.startswith("(STOP)") or l.startswith("(END)"):
            in_body = False
            continue
        elif l.startswith("(START)"):
            in_body = True
            data["body"] = ""
            continue
        elif in_body:
            data["body"] += l
            continue
        get_value(l, "TITLE=", "title")
        get_value(l, "C=", "categories")
        get_value(l, "DATE=", "date")
        get_value(l, "NUMBER=", "number")
    f.close()
    filename = os.path.basename(file)
    obj = BlogPost(filename, data["title"], data["date"], data["categories"], data["number"], data["body"])
    post_objects.append(obj)
    data.clear()

### Sort post_objects. (Default: By date, newest to oldest. With command line options, it is also possible to sort by filename (-f), title (-t), or meatadata number (-n). These will also be sorted from highest to lowest. To sort from oldest to newest / lowest to highest, use the command line option (-r).

if file_mode:
    post_objects.sort(key=attrgetter("filename"), reverse=reverse_mode)
elif number_mode:
    post_objects.sort(key=attrgetter("number"), reverse=reverse_mode)
elif title_mode:
    post_objects.sort(key=attrgetter("title"), reverse=reverse_mode)
# Converts date to datetime object for sorting by date. These are then deleted.
# Possible performance issues caused by creating date objects inside the sort() method, so this was avoided to be safe: https://stackoverflow.com/questions/10123953/how-to-sort-an-object-array-by-date-property#comment100564234_10124053
else:
    for obj in post_objects:
        if len(obj.date) == 2:
            obj.date_dt = datetime.datetime.strptime(" ".join(obj.date), '%m/%d/%y %H:%M')
        elif len(obj.date) == 1:
            obj.date_dt = datetime.datetime.strptime(obj.date[0], '%m/%d/%y')
        else:
            print("DATE value in source file '" + obj.filename + "' is written incorrectly. Please ensure that it is written in MM/DD/YY format or MM/DD/YY Hour:Minute (24hr) format.")
            sys.exit(2)
    post_objects.sort(key=attrgetter("date_dt"), reverse=reverse_mode)
    for obj in post_objects:
        del obj.date_dt

# Set up a function that creates a temp copy of post_template and finds and replaces values in the template with fields of the current object. This function is called format_post in the outline and ideas textfiles
