## Proof that previous_bold_or_italics never becomes equal to "bold" for some reason.
### = Annotation for section of code
## = Todo
# = General annotations, explains pieces of code.

import os
import sys, getopt
import configparser
import datetime
import shutil
from operator import attrgetter

### Handle command line options/arguments
args = sys.argv[1:]
short_options = "htnfrc:o:"
long_options = ["help", "sort-by-title", "sort-by-number", "sort-by-filename", "reversed", "config=", "output="]
try:
    arguments, trailing = getopt.getopt(args, short_options, long_options)
except getopt.GetoptError as err:
    print(err)
    sys.exit(2)

# By default search for config in the same directory as where this script is located.
# If the user is already in the directory where the config and script are located (and therefore script_dir==""), then don't add a "/" before "config.ini"
script_dir = os.path.dirname(sys.argv[0])
if script_dir == "":
    config = "config.ini"
else:
    config = script_dir + "/config.ini"

reverse_mode = True
file_mode = False
number_mode = False
title_mode = False
custom_output = False
for option, value in arguments:
    if option in ("-c", "--config"):
        config = os.path.expanduser(value)
    elif option in ("-o", "--output"):
        custom_output = True
        try:
            os.mkdir(value)
        except:
            pass
        output_dir = os.path.expanduser(value)
        output_dir = os.path.abspath(output_dir) + "/"
    elif option in ("-h", "--help"):
        print("Usage: generator.py [OPTIONS]")
        print("Options:")
        print("(DEFAULT: Posts are sorted by date, newest to oldest)")
        print("-h, --help\tPrint this help text and exit")
        print("-t, --sort-by-title\tSort posts by title")
        print("-f, --sort-by-filename\tSort posts by filename")
        print("-n, --sort-by-number\tSort posts by metadata number (entered in the NUMBER= field of a source file")
        print("-r, --reversed\tSort posts in reverse order, from lowest to highest / oldest to newest.")
        print("-c 'path/to/config', --config='path/to/config'\tManually specify the configuration file to be used for this run of the script.")
        print("-o 'path/to/output/directory', --output='path/to/output/directory'\tManually specify the output directory (Avoid overwriting the contents of the default output directory specified in the configuration file)")
        print("\nFor more information and a user guide, see README.md\nAvailable online at: https://github.com/chsf21/3s/")
        sys.exit(0)
    elif option in ("-t", "--sort-by-title"):
        title_mode = True
    elif option in ("-n", "--sort-by-number"):
        number_mode = True
    elif option in ("-r", "--reversed"):
        # Reverse mode: First post appears first on the site
        # Without reverse mode (default): Last post appears first on the site
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
            print(f"The option {key} is missing from the config file: {config}")
            print(f"For information on how to set up and write the config file, please see the documentation at: https://github.com/chsf21/3s/")
            sys.exit(2)

validate_config(config, 'Paths', ['OutputDirectory', 'SourceDirectory', 'PageTemplate', 'PostTemplate', 'NavigationTemplate'])

# Get paths (by expanding them properly into absolute paths). Check if paths specified in config file point to existing files and directories.
def get_path(config, section, key, item_name, is_directory):
    # If a relative path was written in the config file, interpret it relative to the location of the config file.
    if iniparser[section][key].startswith('/') or iniparser[section][key].startswith('~'):
        path = os.path.expanduser(iniparser[section][key])
    else:
        path = os.path.dirname(config) + "/" +  iniparser[section][key]
    exists = os.path.isdir(path) if is_directory else os.path.isfile(path)
    if exists:
        # Paths are saved as absolute. This may come at some cost to memory when saving a very large list of file paths to source_files. However, the concreteness that is gained from using absolute paths may be worth the increased memory size, especially on modern computers.
        path = os.path.abspath(path)
        if is_directory:
            return path + "/"
        else:
            return path
    else:
        print(f"Could not find the {item_name} at: {path}")
        print(f"Config file in which the location of the {item_name} was specified: {config}")
        print(f"\nPlease ensure that the location specified in the config file represents the true location of the {item_name}.")
        print("\nAlso note that relative paths specified in the config file will be interpreted relative to the location of the config file.")
        print(f"\nIf {item_name} does not exist yet, please create it manually.")
        sys.exit(2)

if not custom_output:
    output_dir = get_path(config, 'Paths', 'OutputDirectory', "output directory", is_directory=True)
source_dir = get_path(config, 'Paths', 'SourceDirectory', "source directory", is_directory=True)
page_template = get_path(config, 'Paths', 'PageTemplate', "page template", is_directory=False)
post_template = get_path(config, 'Paths', 'PostTemplate', "post template", is_directory=False)
navigation_template = get_path(config, 'Paths', 'NavigationTemplate', "navigation template", is_directory=False)

### Create objects for blog posts located in source_dir
### Source files will be parsed for metadata and body text, which will then be saved in object properties
post_objects = list()
number = 1
class BlogPost:
    def __init__(self, path, filename, title, date, categories, meta_number, body):
        self.path = path
        self.filename = filename
        self.title = title
        self.date = date
        self.categories = categories
        self.meta_number = meta_number
        self.body = body
        self.number = number

    # Fix year that was accidentally written as 4 digits instead of 2
    def fix_year(self):
        date_year = self.date[0].split("/")[2]
        if len(date_year) == 4:
            self.date[0] = self.date[0][:-4] + date_year[-2:]

# Traverse the source_dir recursively and save files to source_files list
# Symlinks are not followed to prevent an error where os.walk enters an infinite loop
source_files = list()
for rootdir, dirnames, filenames in os.walk(source_dir, topdown=True, followlinks=False):
    for file in filenames:
        if not file.endswith('.txt') or not file.endswith('') or file.startswith('.'):
            continue
        file_path = os.path.join(rootdir, file)
        source_files.append(file_path)

# Function for pulling metadata out of a source file and saving it to a dict
data = dict()
def get_value(dictionary, line, source_key, dict_key):
    if line.startswith(source_key):
        dictionary[dict_key] = line.removeprefix(source_key)
        dictionary[dict_key] = dictionary[dict_key].removesuffix('\n')
        if source_key in ("C=", "CATEGORIES=", "CATEGORY="):
            dictionary[dict_key] = dictionary[dict_key].split(",")
        elif source_key == "DATE=":
            dictionary[dict_key] = dictionary[dict_key].split(" ")
        return True
    else:
        # If no key is found in the source file, then the dictionary key should equal the empty string.
        # Since setting date to the empty string can cause issues (when trying to convert date into a datetime object for sorting), date will be given a default value when set to the empty string (see below)
        if dict_key not in dictionary.keys():
            dictionary[dict_key] = ""
        return False

# Go through source file line by line. If metadata is encountered, parse it and save it to a dict. Parse body text.
in_body = False
for file in source_files:
    if os.path.getsize(file) == 0:
        continue
    with open(file, "r") as f:
        ## Handle errors caused by having two "tags" on the same line
        ## Print an appropriate error message. If you can, it's even better to make it so that (START) and (STOP) don't need to be on their own lines.
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
            else:
                if get_value(data, l, "TITLE=", "title"):
                    continue
                elif get_value(data, l, "C=", "categories"):
                    continue
                elif get_value(data, l, "CATEGORY=", "categories"):
                    continue
                elif get_value(data, l, "CATEGORIES=", "categories"):
                    continue
                elif get_value(data, l, "DATE=", "date"):
                    continue
                elif get_value(data, l, "NUMBER=", "meta_number"):
                    continue
    filename = os.path.basename(file)
    obj = BlogPost(file, filename, data["title"], data["date"], data["categories"], data["meta_number"], data["body"])
    post_objects.append(obj)
    data.clear()

### Sort post_objects. (Default: By date, newest to oldest. With command line options, it is also possible to sort by filename (-f), title (-t), or meatadata number (-n). These will also be sorted from highest to lowest. To sort from oldest to newest / lowest to highest, use the command line option (-r).

def default_date(obj):
    print("Could not extract date. Defaulting to 01/01/00 for " + obj.filename + "'s date. No date will be displayed for this post on the generated website.")
    obj.date = ""
    obj.date_dt = datetime.datetime.strptime("01/01/00", '%m/%d/%y')

if file_mode:
    post_objects.sort(key=attrgetter("filename"), reverse=reverse_mode)
elif number_mode:
    post_objects.sort(key=attrgetter("meta_number"), reverse=reverse_mode)
elif title_mode:
    post_objects.sort(key=attrgetter("title"), reverse=reverse_mode)
# Converts date to datetime object for sorting by date. These are then deleted.
# Possible performance issues caused by creating date objects inside the sort() method, so this was avoided to be safe: https://stackoverflow.com/questions/10123953/how-to-sort-an-object-array-by-date-property#comment100564234_10124053
else:
    for obj in post_objects:
        # If an hour was given for DATE=
        if len(obj.date) == 2:
            obj.fix_year()
            try:
                obj.date_dt = datetime.datetime.strptime(" ".join(obj.date), '%m/%d/%y %H:%M')
            except:
                default_date(obj)
        # If no hour was given
        elif len(obj.date) == 1:
            obj.fix_year()
            try:
                obj.date_dt = datetime.datetime.strptime(obj.date[0], '%m/%d/%y')
            except:
                default_date(obj)
        # If no date was given, default to 01/01/2000 for sorting purposes. (That default date will not display on the generated website.)
        elif obj.date == "":
            obj.date_dt = datetime.datetime.strptime("01/01/00", '%m/%d/%y')
        # If the date was formatted incorrectly (more than two arguments, so likely not just MM/DD/YY and Hour:Minute), try to extract the proper date.
        else:
            print("DATE value in source file '" + obj.filename + "' is written incorrectly. Please ensure that it is written in MM/DD/YY format or MM/DD/YY Hour:Minute (24hr) format.")
            obj.date = obj.date[:2]
            obj.fix_year()
            try:
                obj.date_dt = datetime.datetime.strptime(" ".join(obj.date), '%m/%d/%y %H:%M')
            except:
                default_date(obj)
            else:
                print("Attempted to extract date regardless. Date for " + obj.filename + " may display incorrectly.")

    post_objects.sort(key=attrgetter("date_dt"), reverse=reverse_mode)
    for obj in post_objects:
        del obj.date_dt

### Assign post numbers to all objects (numbers reflect the actual order of posts in the list post_objects. 
# This is different from meta_number, which corresponds with the optional "NUMBER=" field in source files. meta_number is used to facilitate sorting by number with -n. If the user does not sort by -n, then meta_number may not represent the actual position of an object in post_objects.)

# Note: reverse_mode is False when the user selects -r (see above near beginning of file)
if reverse_mode == False:
    for obj in post_objects:
        obj.number = str(number)
        number += 1
else:
    for obj in reversed(post_objects):
        obj.number = str(number)
        number += 1

### Functions for handling italics * and bold ** markers.
### Used later in the function format_post
def handle_bold(string_as_list, index, bold_encountered_flag, previous_tracker):
    if string_as_list[index] == "*" and string_as_list[index + 1] == "*":
        if bold_encountered_flag == False:
            string_as_list[index] = "<strong>"
            string_as_list[index + 1] = ""
            return True, "bold"
        else:
            string_as_list[index] = "</strong>"
            string_as_list[index + 1] = ""
            return False, "bold"
    else:
        return bold_encountered_flag, previous_tracker

def handle_italics(string_as_list, index, italics_encountered_flag, previous_tracker):
    # If there is a * at the end of a line (string_as_index), it is definitely there to mark italics and not bold (as bold would require two characters: **). This piece of code is necessary, because it allows us to avoid evaluating [index + 1] when at the end of a line, which would return an error.
    if index == (len(string_as_list) - 1) and string_as_list[index] == "*":
        if italics_encountered_flag == False:
            string_as_list[index] = "<em>"
            return True, "italics"
        else:
            string_as_list[index] = "</em>"
            return False, "italics"
    elif string_as_list[index] == "*" and not string_as_list[index + 1] == "*":
        if italics_encountered_flag == False:
            string_as_list[index] = "<em>"
            return True, "italics"
        else:
            string_as_list[index] = "</em>"
            return False, "italics"
    else:
        return italics_encountered_flag, previous_tracker

def handle_code(string_as_list, index, code_encountered_flag):
    if string_as_list[index] == "`" and string_as_list[index + 1] == "`" and string_as_list[index + 2] == "`":
        if code_encountered_flag == False:
            string_as_list[index] = "<code>"
            string_as_list[index + 1] = ""
            string_as_list[index + 2] = ""
            return True
        else:
            string_as_list[index] = "</code>"
            string_as_list[index + 1] = ""
            string_as_list[index + 2] = ""
            return False
    else:
        return code_encountered_flag

### Function for finding and replacing tags in post_template with post object properties. Also formats content within the body of the source file.
### Returns the formatted post as a string
def format_post(obj):
    with open(post_template, "r") as f:
        temp = f.read()
        temp = temp.replace("(NUMBER)", obj.number)
        temp = temp.replace("(TITLE)", obj.title)
        temp = temp.replace("(DATE)", " ".join(obj.date))
        temp = temp.replace("(CATEGORIES)", ", ".join(obj.categories))
        temp_body = obj.body
    # Process formatting within the body of the source file
    italics_encountered = False
    bold_encountered = False 
    code_encountered = False 
    previous_bold_or_italics = "italics"
    for line in temp_body.splitlines():
        if line.startswith("(IMAGE"):
            # Does not literally mean "image arguments". It is a list containing ["(IMAGE", "path/to/image", "id"] (if an id is specified. id is optional.)
            image_args = line.split(" ")

            if len(image_args) > 3:
                print(f"Too many arguments given to (IMAGE) in source file {obj.filename}.") 
                print("Please format (IMAGE) as: (IMAGE path/to/image [id])")
                print("Script will continue anyway. Post for {obj.filename} will not display image correctly.\n")
                continue
            elif len(image_args) < 2:
                print(f"No arguments given to (IMAGE) in source file {obj.filename}.")
                print("Please format (IMAGE) as: (IMAGE path/to/image [id])")
                print("Script will continue anyway. Post for {obj.filename} will not display image correctly.\n")
                continue

            image_args[-1] = image_args[-1].removesuffix(")")
            # If an image's path is given as a relative path, expand it relative to the location of the source file.
            if image_args[1].startswith("/") or image_args[1].startswith("~"):
                img_path = os.path.expanduser(image_args[1])
            else:
                img_path = os.path.dirname(obj.path) + "/" + image_args[1]
            
            if len(image_args) == 3:
                img_line = f"</p><img src=\"{img_path}\" id=\"{image_args[2]}\"><p>"
                temp_body = temp_body.replace(line, img_line)
            else:
                img_line = f"</p><img src=\"{img_path}\"><p>"
                temp_body = temp_body.replace(line, img_line)
            continue
        else:
            # Interpreting * and ** as italics and bold tags respectively
            # Code is marked with ```. If an opening tag for code is found, * and ** will be ignored until the next ``` is found.
            ## Add continue statements here (?) Or maybe that is redundant, since the whole thing is built with if and else statements, and adding continues will make the code less readable.
            formatted_line = list(line)
            for char_num in range(len(formatted_line)):
                if char_num > 0 and formatted_line[char_num - 1] == "\\":
                    formatted_line[char_num - 1] = ""
                # The last character of a line can not possibly be a bold tag because bold tags are two characters: **
                elif char_num == (len(formatted_line) - 1) and not code_encountered:
                    italics_encountered, previous_bold_or_italics = handle_italics(formatted_line, char_num, italics_encountered, previous_bold_or_italics)
                # Similarly the second-to-last character of a line can not possibly be a code tag because code tags are three characters: ``
                elif char_num == (len(formatted_line) - 2) and not code_encountered:
                    italics_encountered, previous_bold_or_italics = handle_italics(formatted_line, char_num, italics_encountered, previous_bold_or_italics)
                    bold_encountered, previous_bold_or_italics = handle_bold(formatted_line, char_num, bold_encountered, previous_bold_or_italics)
                else:
                    if code_encountered:
                        code_encountered = handle_code(formatted_line, char_num, code_encountered)
                        continue
                    # If three sequential asterisks *** are found, it is ambiguous whether to interpret this as <em><strong> or <strong><em>. This can lead to incorrect HTML nesting. In order to this, the order in which asterisks are replaced should depend on whether a bold or italics tag was seen more recently.
                    elif formatted_line[char_num] == "*" and formatted_line[char_num + 1] == "*" and formatted_line[char_num + 2] == "*":
                        if previous_bold_or_italics == "italics":
                            # The function handle_italics isn't used here, as it will not trigger, since the * is followed by an *.
                            # Instead of using handle_italics, the * is replaced manually.
                            if italics_encountered == False:
                                formatted_line[char_num] = "<em>"
                                italics_encountered = True
                                previous_bold_or_italics = "italics"
                            else:
                                formatted_line[char_num] = "</em>"
                                italics_encountered = False
                                previous_bold_or_italics = "italics"
                        else:
                            bold_encountered, previous_bold_or_italics = handle_bold(formatted_line, char_num, bold_encountered, previous_bold_or_italics)
                    else:
                        code_encountered = handle_code(formatted_line, char_num, code_encountered)
                        italics_encountered, previous_bold_or_italics = handle_italics(formatted_line, char_num, italics_encountered, previous_bold_or_italics)
                        bold_encountered, previous_bold_or_italics = handle_bold(formatted_line, char_num, bold_encountered, previous_bold_or_italics)
            temp_body = temp_body.replace(line, ''.join(formatted_line))
    temp_body = temp_body.replace("\n", "<br>")
    temp_body = temp_body.replace("\t", "&emsp;")
    temp = temp.replace("(BODY)", temp_body) 
    return temp

### Remove any .html files that are currently in the output directory that were not created during this run of the script. This is to provide "overwrite" functionality.

existing_files = os.listdir(output_dir)
for existing_file in existing_files:
    if existing_file.endswith(".html"):
        os.remove(output_dir + "/" + existing_file)

### Insert formatted posts (returned by format_post) into page_template. Create a new page when necessary.
# first_page_filename should be a the filename of the *first* .html file to be generated. For example: "index"
# subsequent_page_filename should be the filename of all subsequently generated .html files. These files will look like: page_filename[page number].html
# formatted_posts should be a list of posts that were already formatted by the function format_post.
def insert_posts(first_page_filename, subsequent_page_filename, formatted_posts):
    # page_count increases every time a new page is created and is used in the filename of the generated .html file.
    # This is besides for the first page, which will have the filename of whatever is passed as "current_page"
    # Therefore page_count should start at 2
    page_count = 2
    post_count = 0
    current_page = shutil.copyfile(page_template, output_dir + first_page_filename + ".html")
    page_list = list()
    page_list.append(current_page)
    while post_count < len(formatted_posts):
        with open(current_page, "r") as f:
            contents = f.read()
            posts_per_page = contents.count("(POST)")
        for x in range(posts_per_page):
            if post_count == len(formatted_posts):
                contents = contents.replace("(POST)", "")
                break
            contents = contents.replace("(POST)", formatted_posts[post_count], 1)
            post_count += 1
        with open(current_page, "w") as f:
            f.write(contents)
        if post_count == len(post_objects):
            break
        else:
            new_page = output_dir + subsequent_page_filename + str(page_count) + ".html"
            current_page = shutil.copyfile(page_template, new_page)
            page_list.append(new_page)
            page_count += 1
    return page_list

# Loop through every object in post_objects. For each object, format it using format_post and append it to the list formatted_posts. 
formatted_posts = list()
for obj in post_objects:
    formatted_posts.append(format_post(obj))
# Call insert_posts to generate .html pages in output_dir for every post. Save paths of generated pages to list pages.
pages = insert_posts("index", "page", formatted_posts)

### Format the navigation_template
with open(navigation_template, "r") as f:
    navigation = f.read()

first = ""
previous = ""
nxt = ""
last = "" 
for line in navigation.splitlines():
    if "(FIRST)" in line:
        first = line
        continue
    elif "(PREVIOUS)" in line:
        previous = line
        continue
    elif "(NEXT)" in line:
        nxt = line
        continue
    elif "(LAST)" in line:
        last = line
        continue

page_numbers = range(len(pages))

# Format the navigation_template appropriately
def format_navigation(page_number):
    formatted_nav = navigation
    # Remove necessary lines from the formatted navigation_template
    # The first page should not contain hyperlinks for (FIRST) or (PREVIOUS)
    # The last page should not contain hyperlinks for (LAST) or (NEXT)
    first_page = False
    last_page = False
    if page_number == 0:
        formatted_nav = formatted_nav.replace(first, "")
        formatted_nav = formatted_nav.replace(previous, "")
        first_page = True
    elif page_number == page_numbers[-1]:
        formatted_nav = formatted_nav.replace(last, "")
        formatted_nav = formatted_nav.replace(nxt, "")
        last_page = True

    # Replace keywords in navigation_template with appropriate values
    if not first_page:
        new_previous = previous.replace("(PREVIOUS)", os.path.basename(pages[page_number - 1]))
        formatted_nav = formatted_nav.replace(previous, new_previous)
        new_first = first.replace("(FIRST)", os.path.basename(pages[0]))
        formatted_nav = formatted_nav.replace(first, new_first)
    if not last_page:
        new_nxt = nxt.replace("(NEXT)", os.path.basename(pages[page_number + 1]))
        formatted_nav = formatted_nav.replace(nxt, new_nxt)
        new_last = last.replace("(LAST)", os.path.basename(pages[len(pages) - 1]))
        formatted_nav = formatted_nav.replace(last, new_last)
    return formatted_nav

### Find and replace for all remaining keywords on page_template
### (all keywords which could not be replaced earlier in the script when the initial .html files were outputted) 

# Replace (NAVIGATION) in the page_template with the result of format_navigation
# Replace (NUMBER) in the page_template with the current page number
def process_pages(page_number):
    with open(pages[page_number], "r") as f:
        contents = f.read()
    contents = contents.replace("(NAVIGATION)", format_navigation(page_number))
    contents = contents.replace("(NUMBER)", str(page_number + 1))
    with open(pages[page_number], "w") as f:
        f.write(contents)

for page_number in page_numbers:
    process_pages(page_number)

