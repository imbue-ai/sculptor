# Release process for Sculptor v1

## TL;DR
The Release Process for Sculptor v1 is intentionally designed to be lightweight
and manual for maximum flexibility. As we grow in levels of sophistication, we
will add to this process.

* We employ a variation upon the [Release Branch](https://martinfowler.com/articles/branching-patterns.html#release-branch) strategy (as described at that link by Martin Fowler)

* We align on 3 release channels: stable, internal, latest

* **Stable**: Has been tested, and is what our customers use
* **Internal**: If there is a release candidate, internal is aliased to this. Otherwise, this is stable.
* **Latest**: This is intended to be what was most recently merged to main.

A Release Branch is regularly and explicitly cut by the Release Coordinator.
There is a short period of time when that branch is used by all internal
Imbumans to drive out any blocking bugs. At the end of this period, that branch
becomes the new stable release.


### Goals

* Keep our velocity high. Developers should not have to worry (too much) about where we are in the release process
* Ensure we have enough confidence in our builds before we release them to the public. Specifically, each build will have enough time with internal testing to find any errors
* Enable us to directly fix any errors discovered during the release independently.
* Isolate fixing the release from other work


### Initiate a release cut
The [Runbook is here](https://www.notion.so/imbue-ai/Cut-a-new-Release-of-Sculptor-234a550faf9580dc9502ea403a5ab425)

You can only cut a release from main with a clean state.

The version that will be built will be determined from the version of sculptor
in `pyproject.toml`.

This will create [a clean build of the distribution artifacts](packaging.md),
and it will upload these artifacts to the correct locations.

A copy will be uploaded to:

* s3://imbue-sculptor-releases/sculptor-{version}.tar.gz

This release will also be uploaded to

* s3://imbue-sculptor-latest/internal/sculptor.tar.gz

which is what everyone internally should be using.


### Promoting a release

The [Runbook on promoting the release](https://www.notion.so/imbue-ai/Promote-a-new-Release-of-Sculptor-v1-223a550faf9580b2adbbc0e11f1650e4) is here.

You can only cut a release from the release branch, with a clean state.

This will create a new build, and upload the build artifacts to the correct location.

A copy will be uploaded to:

* s3://imbue-sculptor-releases/sculptor-{version}.tar.gz

Storing the release version for archival purposes

* s3://imbue-sculptor-latest/sculptor.tar.gz

This is what promotes the version to the public

* s3://imbue-sculptor-latest/internal/sculptor.tar.gz

This sets the internal channel to use the stable version, up until the next cut.


### Fixing up a release

The only changes we should accept into a release branch after it is cut are bug fixes aimed at stabilizing it for the
release.

These fixup changes may be cherry-picked into the release branch from main.

They can also be made directly against the release branch if the cherry-pick would not cleanly apply.

After a fixup change lands, the release coordinator should run

`uv run sculptor/scripts/dev.py fixup-release`

This will bump the release candidate version and publish the artifact to the right places.


### Planned features and future milestones

* Refuse to release a distribution if one already exists (unless --force is passed as an argument to the build)
** “Rc” candidates are exempt from this requirement, and can be rebuilt

#### Milestone 2

* Also publish to PyPI as part of the release
* (tentative, needs vetting) Also publish the releases to Sentry

#### Milestone 3

* Integration with CI: detect the creation of a release branch and start cutting releases based on them.
