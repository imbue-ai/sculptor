# Release process for Sculptor v1

## TL;DR
The Release Process for Sculptor v1 is intentionally designed to be lightweight
and manual for maximum flexibility. As we grow in levels of sophistication, we
will add to this process.


### Initiate a release
Initiate with `uv run sculptor/scripts/dev.py release`

You can only release from main with a clean state.

The version that will be built will be determined from the version of sculptor
in `pyproject.toml`.

This will create [a clean build of the distribution artifacts](packaging.md),
and it will upload these artifacts to the correct locations.

For version tagged releases, these will be uploaded to:

* s3://imbue-sculptor-releases/sculptor-{version}
* s3://imbue-sculptor-releases/sculptor-{version}.tar.gz
* s3://imbue-sculptor-releases/sculptor-{version}-py3-none-any.whl

For now, we always make a fresh build on every release. This will keep us honest
that our builds are repeatable.

### Mark a release as latest

A version-tagged release is not automatically promoted to being the latest
release. There are two ways to promote a tagged release as latest.

You can pass the `--update-latest` flag to the `dev` script at release time:
`uv run sculptor/scripts/dev.py release --update-latest`

You can also call

`uv run sculptor/scripts/dev.py release set-latest-release <version>` which will
update the latest tags to point to the latest release.

The latest version of sculptor is always at

* s3://imbue-sculptor-latest/sculptor
* s3://imbue-sculptor-latest/sculptor.tar.gz
* s3://imbue-sculptor-latest/sculptor-py3-none-any.whl
