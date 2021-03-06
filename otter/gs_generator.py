#################################################
##### Gradescope Generator for Otter-Grader #####
#################################################

import os
import shutil
import argparse
from glob import glob
from subprocess import PIPE
import subprocess
import sys

REQUIREMENTS = """datascience
jupyter_client
ipykernel
matplotlib
pandas
ipywidgets
scipy
seaborn
sklearn
nb2pdf
tornado==5.1.1
otter-grader==0.3.9
"""

SETUP_SH = """#!/usr/bin/env bash

apt-get install -y python3 python3-pip

pip3 install -r /autograder/source/requirements.txt
"""

def main():
	# TODO: add overriding max points
	parser = argparse.ArgumentParser(description="Generates zipfile to configure Gradescope autograder")
	parser.add_argument("-t", "--tests-path", nargs='?', dest="tests-path", type=str, default="./tests/", help="Path to test files")
	parser.add_argument("-o", "--output-path", nargs='?', dest="output-path", type=str, default="./", help="Path to which to write zipfile")
	parser.add_argument("-r", "--requirements", nargs='?', type=str, help="Path to requirements.txt file")
	parser.add_argument("--threshold", type=float, default=None, help="Pass/fail score threshold")
	parser.add_argument("--points", type=float, default=None, help="Points possible, overrides sum of test points")
	parser.add_argument("files", nargs='*', help="Other support files needed for grading (e.g. .py files, data files)")
	params = vars(parser.parse_args())

	assert params["threshold"] is None or 0 <= params["threshold"] <= 1, "{} is not a valid threshold".format(
		params["threshold"]
	)

	# format threshold
	RUN_AUTOGRADER = """#!/usr/bin/env python3

from otter.grade import grade_notebook
from glob import glob
import json
import os
import shutil
import subprocess
import re
import pprint
import pandas as pd

SCORE_THRESHOLD = """ + str(params["threshold"]) + """
POINTS_POSSIBLE = """ + str(params["points"]) + """

UTILS_IMPORT_REGEX = r"\\"from utils import [\\w\\*, ]+"
NOTEBOOK_INSTANCE_REGEX = r"otter.Notebook\\(.+\\)"

if __name__ == "__main__":
	# put files into submission directory
	if os.path.exists("/autograder/source/files"):
		for filename in glob("/autograder/source/files/*.*"):
			shutil.copy(filename, "/autograder/submission")

	# create __init__.py files
	subprocess.run(["touch", "/autograder/__init__.py"])
	subprocess.run(["touch", "/autograder/submission/__init__.py"])

	os.chdir("/autograder/submission")

	# check for *.ipynb.json files
	jsons = glob("*.ipynb.json")
	for file in jsons:
		shutil.copy(file, file[:-5])

	nb_path = glob("*.ipynb")[0]

	# fix utils import
	try:
		with open(nb_path) as f:
			contents = f.read()
	except UnicodeDecodeError:
		with open(nb_path, "r", encoding="utf-8") as f:
			contents = f.read()

	contents = re.sub(UTILS_IMPORT_REGEX, "\\"from .utils import *", contents)
	contents = re.sub(NOTEBOOK_INSTANCE_REGEX, "otter.Notebook()", contents)

	try:
		with open(nb_path, "w") as f:
			f.write(contents)
	except UnicodeEncodeError:
		with open(nb_path, "w", encoding="utf-8") as f:
			f.write(contents)

	try:
		os.mkdir("/autograder/submission/tests")
	except FileExistsError:
		pass

	tests_glob = glob("/autograder/source/tests/*.py")
	for file in tests_glob:
		shutil.copy(file, "/autograder/submission/tests")

	scores = grade_notebook(nb_path, tests_glob, name="submission", ignore_errors=True, gradescope=True)
	# del scores["TEST_HINTS"]

	output = {"tests" : []}
	for key in scores:
		if key != "total" and key != "possible":
			output["tests"] += [{
				"name" : key,
				"score" : scores[key]["score"],
				"possible": scores[key]["possible"],
				"visibility": ("visible", "hidden")[scores[key]["hidden"]]
			}]
			if "hint" in scores[key]:
				output["tests"][-1]["output"] = repr(scores[key]["hint"])
	output["visibility"] = "hidden"

	if POINTS_POSSIBLE is not None:
		output["score"] = scores["total"] / scores["possible"] * POINTS_POSSIBLE

	if SCORE_THRESHOLD is not None:
		if scores["total"] / scores["possible"] >= SCORE_THRESHOLD:
			output["score"] = POINTS_POSSIBLE or scores["possible"]
		else:
			output["score"] = 0

	with open("/autograder/results/results.json", "w+") as f:
		json.dump(output, f)

	print("\\n\\n")
	df = pd.DataFrame(output["tests"])
	if "output" in df.columns:
		df.drop(columns=["output"], inplace=True)
	# df.drop(columns=["hidden"], inplace=True)
	print(df)
"""

	# create tmp directory to zip inside
	os.mkdir("./tmp")

	# copy tests into tmp
	os.mkdir(os.path.join("tmp", "tests"))
	for file in glob(os.path.join(params["tests-path"], "*.py")):
		shutil.copy(file, os.path.join("tmp", "tests"))

	reqs = REQUIREMENTS

	if params["requirements"]:
		with open(params["requirements"]) as f:
			reqs += f.read()

	# copy requirements into tmp
	with open(os.path.join(os.getcwd(), "tmp", "requirements.txt"), "w+") as f:
		f.write(reqs)

	# write setup.sh and run_autograder to tmp
	with open(os.path.join(os.getcwd(), "tmp", "setup.sh"), "w+") as f:
		f.write(SETUP_SH)

	with open(os.path.join(os.getcwd(), "tmp", "run_autograder"), "w+") as f:
		f.write(RUN_AUTOGRADER)

	# copy files into tmp
	if len(params["files"]) > 0:
		os.mkdir(os.path.join("tmp", "files"))

		for file in params["files"]:
			if file == "gen":
				continue
			shutil.copy(file, os.path.join(os.getcwd(), "tmp", "files"))

	os.chdir("./tmp")

	zip_cmd = ["zip", "-r", os.path.join("..", params["output-path"], "autograder.zip"), "run_autograder",
			   "setup.sh", "requirements.txt", "tests"]

	if params["files"]:
		zip_cmd += ["files"]

	zipped = subprocess.run(zip_cmd, stdout=PIPE, stderr=PIPE)

	if zipped.stderr.decode("utf-8"):
		raise Exception(zipped.stderr.decode("utf-8"))

	# move back to tmp parent directory
	os.chdir("..")

	# delete tmp directory
	shutil.rmtree("tmp")

if __name__ == "__main__":
	main()
