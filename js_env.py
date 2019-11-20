import re
import os
import shlex
import subprocess
import datetime
import configparser
import argparse
from glob import glob
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from flask import Flask
from threading import Thread


def which(program):
    """
    This function is taken from
    http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
    """
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None


class Singleton:
    """
    A non-thread-safe helper class to ease implementing singletons.
    This should be used as a decorator -- not a metaclass -- to the
    class that should be a singleton.

    The decorated class can define one `__init__` function that
    takes only the `self` argument. Other than that, there are
    no restrictions that apply to the decorated class.

    To get the singleton instance, use the `Instance` method. Trying
    to use `__call__` will result in a `TypeError` being raised.

    Limitations: The decorated class cannot be inherited from.

    This singleton class is taken from
    http://stackoverflow.com/questions/42558/python-and-the-singleton-pattern

    """

    def __init__(self, decorated):
        self._decorated = decorated

    def Instance(self):
        """
        Returns the singleton instance. Upon its first call, it creates a
        new instance of the decorated class and calls its `__init__` method.
        On all subsequent calls, the already created instance is returned.

        """
        try:
            return self._instance
        except AttributeError:
            self._instance = self._decorated()
            return self._instance

    def __call__(self):
        raise TypeError('Singletons must be accessed through `Instance()`.')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)


class Configuration:
    def __init__(self):
        self._conf = configparser.ConfigParser()
        self._conf.optionxform = str
        self._conf.read('.js_env_config')
        self._excluded_regex = []
        self._excluded_extensions = []
        self._included_extensions = []
        self._excluded_files = []
        self._excluded_folders = ["node_modules"]
        self._commands = ["build", "serve", "start", "test"]
        assert "commands" in self._conf
        assert "server" in self._conf
        assert all([c in self._conf["commands"] for c in self._commands])

    @property
    def server_port(self):
        return self._conf["server"]["port"]

    @property
    def build_command(self):
        return self._conf["commands"]["build"]

    @property
    def test_command(self):
        return self._conf["commands"]["test"]

    @property
    def run_command(self):
        return self._conf["commands"]["run"]

    @property
    def start_command(self):
        return self._conf["commands"]["start"]

    @property
    def serve_command(self):
        return self._conf["commands"]["serve"]

    def set_included_extensions(self, included_file_extensions):
        self._included_extensions = included_file_extensions

    def set_excluded_extensions(self, excluded_file_extensions):
        self._excluded_extensions = excluded_file_extensions

    def set_excluded_regex(self, excluded_filters):
        self._excluded_regex = excluded_filters

    def set_excluded_files(self, excluded_files):
        self._excluded_files = excluded_files

    def set_excluded_folders(self, excluded_folders):
        self._excluded_folders = excluded_folders

    # is_watched requires full relative filepath
    def is_watched(self, filepath):
        watched = False
        for ext in self._included_extensions:
            if filepath.endswith(ext):
                watched = True
        for ext in self._excluded_extensions:
            if filepath.endswith(ext):
                watched = False
        for folder in self._excluded_folders:
            if folder in filepath:
                watched = False
        for fn in self._excluded_files:
            if fn in filepath:
                watched = False
        for regex in self._excluded_regex:
            if re.findall(regex, filepath):
                watched = False
        return watched

    # TODO: This should be cached maybe
    def get_watched(self):
        """Get all the watched files, except for the first level folders
        in self._excluded_folders

        :returns: Watched Files
        :rtype: list
        """
        all_files = [x for x in os.listdir(".") if os.path.isfile(x)]
        all_folders = [x for x in os.listdir(".") if os.path.isdir(x)]
        for x in all_folders:
            if x not in self._excluded_folders:
                all_files.extend(glob(x + '/**', recursive=True))
        elements = [f for f in all_files if self.is_watched(f)]
        return elements


def getext(filename):
    "Get the file extension."
    return os.path.splitext(filename)[-1].lower()


def get_now():
    return datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def build():
    print("Running build", config.build_command)
    if config.build_command:
        subprocess.run(config.build_command, shell=True)
    return "Building"


def test():
    print("Running \"test\"")
    if config.test_command:
        subprocess.run(shlex.split(config.test_command), shell=True)
    return "Testing"


def start():
    print("Running \"start\"")
    if config.start_command:
        subprocess.run(shlex.split(config.start_command), shell=True)
    return "Starting"


def run():
    print("Running \"run\"")
    if config.run_command:
        subprocess.run(shlex.split(config.run_command), shell=True)
    return "Running"


# TODO: serve is a persistent command, should't be issued like that.
#       Or perhaps if serve is called again, then simply stop the
#       process and run again
def serve():
    print("Running \"serve\"")
    if config.run_command:
        subprocess.run(config.serve_command, shell=True)
    return "Serving"


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, root='.'):
        self.root = root
        self.config = config

    def _build_if_watched(self, filepath):
        if os.path.isfile(filepath):
            pwd = os.path.abspath(self.root) + '/'
            # print("filepath", filepath, pwd, pwd in filepath)
            filepath = str(filepath)
            assert pwd in filepath
            filepath = filepath.replace(pwd, '')
            watched = self.config.is_watched(filepath)
            if watched:
                print("file " + filepath + " is watched")
                build()
            else:
                # print("file " + filepath + " is not watched")
                pass
        else:
            # print(filepath + " is not a file")
            pass

    def on_created(self, event):
        print("file " + event.src_path + " created")
        self._build_if_watched(event.src_path)

    def on_modified(self, event):
        print("file " + event.src_path + " modified")
        self._build_if_watched(event.src_path)

    def on_deleted(self, event):
        print("file " + event.src_path + " deleted")
        self._build_if_watched(event.src_path)


# TODO: Display config.
# TODO: config should be reparseable, i.e., from an http wrapper if
#       parse is called, config should be generated again.
config = Configuration()
def parse_options():
    parser = argparse.ArgumentParser(description="Watcher for JS node env")
    parser.add_argument("-w", "--watchdog", type=str, default="True",
                        help="Start watchdog?")
    parser.add_argument("-e", "--exclude", dest="exclusions",
                        default=".pdf,.tex,doc,bin,common,node_modules,build", required=False,
                        help="The extensions (.pdf for pdf files) or the folders to\
        exclude from watch operations separated with commas")
    parser.add_argument("--exclude-filters", dest="exclude_filters",
                        default="#,~,.git", required=False,
                        help="Files with specific regex to exclude. Should not contain ',' ")
    parser.add_argument("--exclude-files", dest="excluded_files",
                        default="", required=False,
                        help="Specific files to exclude from watching")
    parser.add_argument("-i", "--include", dest="inclusions",
                        default=".css,.html,.js,.jsx", required=False,
                        help="The extensions (.pdf for pdf files) or the folders to\
                        exclude from watch operations separated with commas")
    parser.add_argument("--live-server", dest="live_server",
                        action='store_true',
                        help="Start a live server? Requires live-server to be installed\
                        in the nodejs global namespace")
    args = parser.parse_args()
    if args.watchdog.lower() == "true":
        config.watchdog = True
    else:
        config.watchdog = False
    if args.live_server:
        config.live_server = True
    else:
        config.live_server = False

    # since it assumes that extensions startwith '.', I'll remove
    # the check from the globber later
    if args.exclude_filters:
        print("Excluding files for given filters",
              str(args.exclude_filters.split(',')))
        config.set_excluded_regex(args.exclude_filters.split(','))
    if args.inclusions:
        inclusions = args.inclusions
        inclusions = inclusions.split(",")
        config.set_included_extensions(
            [value for value in inclusions if value.startswith(".")])
        if args.excluded_files:
            for ef in args.excluded_files.split(','):
                assert type(ef) == str
            config.set_excluded_files(args.excluded_files.split(','))
    if args.exclusions:
        exclusions = args.exclusions
        exclusions = exclusions.split(",")
        excluded_extensions = [value for value in exclusions if value.startswith(".")]
        excluded_folders = list(set(exclusions) - set(excluded_extensions))
        config.set_excluded_extensions(excluded_extensions)
        config.set_excluded_folders(excluded_folders)


def main():
    npm_path = which("npm")
    if not npm_path:
        print("npm executable must be in the path!")
        exit()
    parse_options()
    if config.live_server:
        print("Starting live server ...")
        p = subprocess.Popen(['live-server', '--open=build'])
        t = Thread(target=p.communicate)
        t.start()
    else:
        print("Not starting live server ...")
    if config.watchdog:
        watched_elements = config.get_watched()
        print("Starting watchdog and watching ", watched_elements)
        event_handler = ChangeHandler()
        observer = Observer()
        observer.schedule(event_handler, os.getcwd(), recursive=True)
        observer.start()
    else:
        print("Not starting watchdog ...")

    port = config.server_port
    app = Flask("npm command server")

    @app.route("/build", methods=["GET", "POST"])
    def __build():
        return build()

    @app.route("/test", methods=["GET", "POST"])
    def __test():
        return test()

    @app.route("/run", methods=["GET", "POST"])
    def __run():
        return run()

    @app.route("/start", methods=["GET", "POST"])
    def __start():
        return start()

    @app.route("/serve", methods=["GET", "POST"])
    def __serve():
        return serve()

    print("Starting server on port %s" % str(port))
    app.run(host="127.0.0.1", port=port)


if __name__ == '__main__':
    main()
