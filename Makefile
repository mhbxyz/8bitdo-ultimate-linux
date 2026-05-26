UV ?= uv

.PHONY: sync test run doctor build clean install-udev uninstall-udev

sync:
	$(UV) sync --extra dev

test:
	$(UV) run pytest

run:
	$(UV) run ultim8do --help

doctor:
	$(UV) run ultim8do doctor

build:
	$(UV) build

install-udev:
	bash ./scripts/install-udev-rules.sh

uninstall-udev:
	rm -f /etc/udev/rules.d/99-8bitdo-ultimate.rules
	udevadm control --reload-rules
	udevadm trigger --subsystem-match=input --subsystem-match=hidraw || true

clean:
	rm -rf .pytest_cache .ruff_cache build dist src/*.egg-info
