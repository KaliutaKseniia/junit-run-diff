# JUnit Run Diff

Find out which tests started failing after a change. This Python CLI compares two JUnit XML reports and shows which tests broke, recovered, appeared, or disappeared. An optional exit code lets CI flag new failures while a team works through known ones.

## Try it

Run the included example with Python 3.10 or newer. It uses the standard library.

~~~sh
git clone https://github.com/KaliutaKseniia/junit-run-diff.git
cd junit-run-diff
python junit_diff.py examples/before.xml examples/after.xml
~~~

The two sample runs each contain six shipping tests. One pickup test broke, a new priority test hit an error, and a previously failing rate calculation passed. The first two sections of the output show those changes.

~~~text
New failures (2)
  shipping.TestQuote::test_pickup  passed -> failed
  shipping.TestQuote::test_priority  absent -> error

Recovered (1)
  shipping.TestQuote::test_remote_area  failed -> passed
~~~

## Use it in CI

Save the same test job's JUnit XML from two runs. With pytest, `python -m pytest --junit-xml=report.xml` writes a report. Supply the older file first.

~~~sh
python junit_diff.py before.xml after.xml --format json --fail-on-new
~~~

| Exit code | Meaning |
| --- | --- |
| 0 | Comparison completed. With `--fail-on-new`, this means there were zero new failures. |
| 1 | `--fail-on-new` found at least one new failure or error. The report is still printed. |
| 2 | Invalid arguments, unreadable files, or an invalid or ambiguous report. Details go to standard error. |

## How the comparison works

Tests are matched by the pair `(classname, name)`. Parameterized names are preserved. A missing class name is treated as an empty string. Each pair must appear only once per input file. If your CI matrix repeats the same tests, compare the reports for each job separately.

| Group | What happened in the current run |
| --- | --- |
| New failures | A passing, skipped, or newly added test now fails or errors. |
| Recovered | A previously failing or errored test passed. |
| Still failing | Both runs recorded a failure or error for the same test. |
| Added or removed | A test appeared or disappeared. A newly added failure goes in New failures. |
| Other status changes | A test was skipped after it ran, or a previously skipped test passed. |

Passing or skipped tests with the same outcome in both runs contribute to the unchanged count. When a test disappears or gets skipped, its row records that transition. The JSON report keeps class names and test names in separate fields and represents absence as `null`.

## Run the tests

~~~sh
python -m unittest discover -s tests -v
~~~
