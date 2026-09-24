.PHONY: run test demo
run:
	python -m expertloop serve

test:
	python -m pytest

demo:
	python -m expertloop demo
