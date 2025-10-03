import copy
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from jinja2 import ChoiceLoader
from jinja2 import Environment
from jinja2 import PackageLoader
from jinja2 import select_autoescape
from junit2htmlreport.parser import Case
from junit2htmlreport.parser import Class
from junit2htmlreport.parser import Junit
from junit2htmlreport.parser import NO_CLASSNAME
from junit2htmlreport.parser import ParserError
from junit2htmlreport.parser import Property
from junit2htmlreport.parser import Suite
from junit2htmlreport.parser import clean_xml_attribute
from junit2htmlreport.render import HTMLReport

from sculptor.cli.dev_commands.run_tests.constants import ANSI_PATTERN


def add_stdout_to_report(junit_report: ElementTree, stdout: str, stderr: str) -> bool:
    # find the only test case:
    testcase = junit_report.find(".//testcase")

    if testcase is None:
        return False

    system_out = ElementTree.SubElement(testcase, "system-out")
    system_out.text = ANSI_PATTERN.sub("", stdout)

    system_err = ElementTree.SubElement(testcase, "system-err")
    system_err.text = ANSI_PATTERN.sub("", stderr)

    return True


def create_junit_report_for_single_test(
    test_args: list[str], stdout: str, stderr: str, duration: float, status="running"
) -> ElementTree.Element:
    test_name = test_args[-1]
    case_name = test_name.split("::", 1)[-1]
    class_name = test_name.split("::", 1)[0]

    # Create the XML structure
    testsuites = ElementTree.Element("testsuites")
    testsuite = ElementTree.SubElement(testsuites, "testsuite")

    # Set basic testsuite attributes
    testsuite.set("name", "pytest")
    testsuite.set("tests", "1")
    testsuite.set("errors", "1" if status == "error" else "0")
    testsuite.set("failures", "1" if status == "failure" else "0")
    testsuite.set("skipped", "1" if status == "skipped" else "0")
    testsuite.set("time", str(duration))
    testsuite.set("timestamp", datetime.now().isoformat())
    testsuite.set("hostname", "localhost")

    # Create the testcase element
    testcase = ElementTree.SubElement(testsuite, "testcase")
    testcase.set("classname", class_name)
    testcase.set("name", case_name)
    testcase.set("time", str(duration))

    skipped = ElementTree.SubElement(testcase, "skipped" if status == "running" else status)
    skipped.set("message", "Test still running..." if status == "running" else f"Test {status}")

    # Add stdout and stderr
    if stdout is not None:
        system_out = ElementTree.SubElement(testcase, "system-out")
        system_out.text = ANSI_PATTERN.sub("", stdout)

    if stderr is not None:
        system_err = ElementTree.SubElement(testcase, "system-err")
        system_err.text = ANSI_PATTERN.sub("", stderr)

    return testsuites


# write atomically
def write_junit_output(junit_report: ElementTree, output_path: Path) -> None:
    temp_file = output_path.with_suffix(".tmp")
    xml_str = '<?xml version="1.0" encoding="utf-8"?>\n' + ElementTree.tostring(junit_report, encoding="utf-8").decode(
        "utf-8"
    )
    with open(temp_file, "w") as f:
        f.write(xml_str)
    temp_file.rename(output_path)


def assemble_reports(commit_hash: str, test_and_output_paths: list[tuple[list[str], Path]], output_file: Path) -> str:
    suite_name = "pytest"
    # Initialize counters for merged testsuite
    total_tests = 0
    total_errors = 0
    total_failures = 0
    total_skipped = 0
    total_time = 0.0
    all_testcases = []

    # Process each input file
    for test_args, input_file in test_and_output_paths:
        if input_file.exists():
            root = ElementTree.parse(input_file).getroot()
        else:
            root = create_junit_report_for_single_test(test_args, "", "", 0.0)

        # Handle case where root is <testsuites> (find the first testsuite)
        if root.tag == "testsuites":
            testsuite = root.find(".//testsuite")
        else:
            testsuite = root

        if testsuite is None:
            print(f"Warning: No testsuite found in {input_file}")
            continue

        # Update counters
        total_tests += int(testsuite.get("tests", 0))
        total_errors += int(testsuite.get("errors", 0))
        total_failures += int(testsuite.get("failures", 0))
        total_skipped += int(testsuite.get("skipped", 0))

        # Add time if available
        if "time" in testsuite.attrib:
            try:
                total_time += float(testsuite.get("time", 0))
            except ValueError:
                pass

        # Collect all testcases
        for testcase in testsuite.findall(".//testcase"):
            testcase_copy = copy.deepcopy(testcase)
            all_testcases.append(testcase_copy)

    # Create the merged XML document
    testsuites = ElementTree.Element("testsuites")
    testsuite = ElementTree.SubElement(testsuites, "testsuite")
    testsuite.set("name", suite_name)
    testsuite.set("errors", str(total_errors))
    testsuite.set("failures", str(total_failures))
    testsuite.set("skipped", str(total_skipped))
    testsuite.set("tests", str(total_tests))
    testsuite.set("time", str(total_time))
    testsuite.set("timestamp", datetime.now().isoformat())
    testsuite.set("hostname", "localhost")

    # Add all testcases to the merged testsuite
    for testcase in all_testcases:
        testsuite.append(testcase)

    write_junit_output(testsuites, output_file)

    # finally, run the html converter:
    html_output_file = Path(output_file).with_suffix(".html")
    # command_args = ["uvx", "junit2html", str(output_file), html_output_file]
    # run_blocking(command_args, timeout=30.0)

    generate_pytest_html_report(commit_hash, Path(output_file), html_output_file, "Test Report")

    return str(html_output_file)


def add_output_links_to_report(junit_report: ElementTree, command_id: str, commit_hash: str):
    for testcase in junit_report.findall(".//testcase"):
        stdout_link = _get_job_s3_prefix_url(commit_hash) + f"{command_id}/stdout.txt"
        testcase.set("stdout-link", stdout_link)

        stderr_link = _get_job_s3_prefix_url(commit_hash) + f"{command_id}/stderr.txt"
        testcase.set("stderr-link", stderr_link)

        # Note: you COULD send everything through as attachments, but this is likely to blow up gitlab
        #  we could just render another report though that actually linked to the thing, but at that point, why bother
        # stdout_line = f"[[ATTACHMENT|/path/to/some/file]]"
        # system_out.text = stdout_line if not system_out.text else system_out.text + "\n\n" + stdout_line + "\n"
        # (same for stderr)


def add_repro_command_to_report(junit_report: ElementTree, repro_command: str):
    for testcase in junit_report.findall(".//testcase"):
        testcase.set("repro-command", repro_command)


class TestJunit(Junit):
    def process(self):
        """
        populate the report from the xml
        :return:
        """
        testrun = False
        suites: "Optional[list[ET.Element]]" = None
        root: "ET.Element"
        if isinstance(self.tree, ET.ElementTree):
            root = self.tree.getroot()
        else:
            root = self.tree

        if root.tag == "testrun":
            testrun = True
            root: "ET.Element" = root[0]

        if root.tag == "testsuite":
            suites = [root]

        if root.tag == "testsuites" or testrun:
            suites = [x for x in root]

        if suites is None:
            raise ParserError("could not find test suites in results xml")
        suitecount = 0
        for suite in suites:
            suitecount += 1
            cursuite = Suite()
            self.suites.append(cursuite)
            cursuite.name = clean_xml_attribute(suite, "name", default="suite-" + str(suitecount))
            cursuite.package = clean_xml_attribute(suite, "package")

            cursuite.duration = float(suite.attrib.get("time", "0").replace(",", "") or "0")

            for element in suite:
                if element.tag == "error":
                    # top level error?
                    errtag = {
                        "message": element.attrib.get("message", ""),
                        "type": element.attrib.get("type", ""),
                        "text": element.text,
                    }
                    cursuite.errors.append(errtag)
                if element.tag == "system-out":
                    cursuite.stdout = element.text
                if element.tag == "system-err":
                    cursuite.stderr = element.text

                if element.tag == "properties":
                    for prop in element:
                        if prop.tag == "property":
                            newproperty = Property()
                            newproperty.name = prop.attrib["name"]
                            newproperty.value = prop.attrib["value"]
                            cursuite.properties.append(newproperty)

                if element.tag == "testcase":
                    testcase = element

                    if not testcase.attrib.get("classname", None):
                        testcase.attrib["classname"] = NO_CLASSNAME

                    if testcase.attrib["classname"] not in cursuite:
                        testclass = Class()
                        testclass.name = testcase.attrib["classname"]
                        cursuite[testclass.name] = testclass

                    testclass: "Class" = cursuite[testcase.attrib["classname"]]
                    newcase = Case()
                    newcase.name = clean_xml_attribute(testcase, "name")
                    newcase.testclass = testclass
                    newcase.duration = float(testcase.attrib.get("time", "0").replace(",", "") or "0")
                    testclass.cases.append(newcase)

                    newcase.stdout_link = testcase.get("stdout-link")
                    newcase.stderr_link = testcase.get("stderr-link")
                    newcase.repro_command = testcase.get("repro-command")

                    # does this test case have any children?
                    for child in testcase:
                        if child.tag == "skipped":
                            newcase.skipped = child.text
                            if "message" in child.attrib:
                                newcase.skipped_msg = child.attrib["message"]
                            if not newcase.skipped:
                                newcase.skipped = "skipped"
                        elif child.tag == "system-out":
                            newcase.stdout = child.text
                        elif child.tag == "system-err":
                            newcase.stderr = child.text
                        elif child.tag in ("failure", "failed"):
                            newcase.failure = child.text
                            if "message" in child.attrib:
                                newcase.failure_msg = child.attrib["message"]
                            if not newcase.failure:
                                newcase.failure = "failed"
                        elif child.tag == "error":
                            newcase.failure = child.text
                            if "message" in child.attrib:
                                newcase.failure_msg = child.attrib["message"]
                            if not newcase.failure:
                                newcase.failure = "error"
                        elif child.tag == "properties":
                            for property in child:
                                newproperty = Property()
                                newproperty.name = property.attrib["name"]
                                newproperty.value = property.attrib["value"]
                                newcase.properties.append(newproperty)


def _get_job_s3_prefix_url(commit_hash: str):
    return f"https://go.snake-blues.ts.net/shared/gitlab-ci-artifacts/{commit_hash}/{os.getenv('CI_JOB_NAME')}/{os.getenv('CI_JOB_ID')}/"


def generate_pytest_html_report(commit_hash: str, xml_path: Path, html_path: Path, title: str) -> None:
    junit = TestJunit(str(xml_path))
    report = HTMLReport(show_toc=True)
    report.load(junit, title=title)

    file_access_url = _get_job_s3_prefix_url(commit_hash)

    template_name = "report.html"
    loaders = [PackageLoader("sculptor.cli.dev_commands.run_tests", "templates")]
    env = Environment(loader=ChoiceLoader(loaders), autoescape=select_autoescape(["html"]))
    template = env.get_template(template_name)
    html_data = template.render(
        report=report, title=report.title, show_toc=report.show_toc, file_access_url=file_access_url
    )

    html_path.write_text(html_data, encoding="utf-8")


if __name__ == "__main__":
    # generate_pytest_html_report(
    #     "whatever", Path("all-test-results/merged_report.xml"), Path("all-test-results/new_report.html"), "Test report"
    # )
    generate_pytest_html_report(
        "whatever", Path("all-test-results/merged_report.xml"), Path("/tmp/new_report.html"), "Test Report"
    )
    # generate_pytest_html_report(Path("/tmp/merged_report.xml"), Path("/tmp/new_report.html"), "Test report")
    # junit_report = ElementTree.fromstring(Path("/tmp/junit.xml").read_text())
    # add_output_links_to_report(junit_report, "mycommandid")
    # add_repro_command_to_report(junit_report, "echo blaoh")
    # write_junit_output(junit_report, Path("/tmp/junit2.xml"))
