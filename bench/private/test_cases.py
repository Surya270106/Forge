"""Grader-only checks. Never copy into an agent execution worktree."""

import unittest

import api
import forgebench as subject
import worker


class Clamp(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.clamp(12, 0, 10), 10)
        self.assertEqual(subject.clamp(-2, 0, 10), 0)

    def test_regression(self):
        self.assertEqual(subject.clamp(5, 0, 10), 5)
        self.assertEqual(subject.clamp(10, 0, 10), 10)


class Port(unittest.TestCase):
    def test_correctness(self):
        for value in ("0", "65536", "abc", " 80", "80.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                subject.parse_port(value)

    def test_regression(self):
        self.assertEqual(subject.parse_port("1"), 1)
        self.assertEqual(subject.parse_port("65535"), 65535)


class Slug(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.slug("  Hello   World  "), "hello-world")
        self.assertEqual(subject.slug("A\tB"), "a-b")

    def test_regression(self):
        self.assertEqual(subject.slug("Hello 2"), "hello-2")


class Divide(unittest.TestCase):
    def test_correctness(self):
        self.assertIsNone(subject.safe_divide(2, 0))

    def test_regression(self):
        self.assertEqual(subject.safe_divide(6, 2), 3)
        self.assertEqual(subject.safe_divide(-6, 2), -3)


class Transition(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.transition("pending", "start"), "running")
        self.assertEqual(subject.transition("running", "finish"), "done")

    def test_regression(self):
        self.assertEqual(subject.transition("pending", "finish"), "pending")
        self.assertEqual(subject.transition("done", "finish"), "done")


class Rows(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.parse_rows("a, b\n\n c,d \n  "), [["a", "b"], ["c", "d"]])

    def test_regression(self):
        self.assertEqual(subject.parse_rows("a,,c"), [["a", "", "c"]])


class Dedupe(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.dedupe(["b", "a", "b", "c", "a"]), ["b", "a", "c"])

    def test_regression(self):
        self.assertEqual(subject.dedupe([]), [])
        self.assertEqual(subject.dedupe(["x"]), ["x"])


class Retry(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.retry_delay(5), 8)
        with self.assertRaises(ValueError):
            subject.retry_delay(-1)

    def test_regression(self):
        self.assertEqual([subject.retry_delay(i) for i in range(4)], [1, 2, 4, 8])


class Runtime(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.choose_runtime("main.TS"), "node")
        with self.assertRaises(ValueError):
            subject.choose_runtime("notes.txt")

    def test_regression(self):
        self.assertEqual(subject.choose_runtime("main.py"), "python")
        self.assertEqual(subject.choose_runtime("main.js"), "node")


class Output(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(subject.limit_output(b"abcdef", 3), b"abc")
        with self.assertRaises(ValueError):
            subject.limit_output(b"x", -1)

    def test_regression(self):
        self.assertEqual(subject.limit_output(b"a", 3), b"a")
        self.assertEqual(subject.limit_output(b"", 0), b"")


class ApiPort(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(api.build_server_config(""), {"port": 8000, "host": "127.0.0.1"})
        with self.assertRaises(ValueError):
            api.build_server_config("70000")

    def test_regression(self):
        self.assertEqual(api.build_server_config("5000"), {"port": 5000, "host": "127.0.0.1"})


class WorkerRetry(unittest.TestCase):
    def test_correctness(self):
        self.assertEqual(worker.retry_schedule(5), [1, 2, 4, 8, 8])
        for attempts in (-1, 6):
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                worker.retry_schedule(attempts)

    def test_regression(self):
        self.assertEqual(worker.retry_schedule(4), [1, 2, 4, 8])
