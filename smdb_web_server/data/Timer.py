from time import perf_counter_ns


class Timer:
    def __init__(self):
        self.start = perf_counter_ns()
        self.end = 0

    def stop(self):
        self.end = perf_counter_ns()

    def __str__(self) -> str:
        return f"{(self.end - self.start) / 1000000}"
