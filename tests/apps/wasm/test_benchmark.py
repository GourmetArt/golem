import os
from unittest import TestCase
from mock import mock_open, patch

from apps.wasm import benchmark
from apps.wasm.task import WasmTaskOptions


class WasmBenchmarkTestCase(TestCase):
    def setUp(self):
        self.benchmark = benchmark.WasmTaskBenchmark()

    def test_definition(self):
        task_def = self.benchmark.task_definition
        self.assertEqual(task_def.subtasks_count, 1)
        self.assertCountEqual(
            task_def.resources,
            [os.path.join(self.benchmark.test_data_dir, 'input')],
        )

        opts: WasmTaskOptions = task_def.options
        self.assertEqual(
            opts.input_dir, os.path.join(self.benchmark.test_data_dir, 'input')
        )
        self.assertEqual(opts.js_name, 'dcraw.js')
        self.assertEqual(opts.wasm_name, 'dcraw.wasm')
        self.assertEqual(len(opts.subtasks), 1)
        self.assertIn('test_subtask', opts.subtasks)

        subtask: WasmTaskOptions.SubtaskOptions = opts.subtasks['test_subtask']
        self.assertEqual(subtask.name, 'test_subtask')
        self.assertEqual(subtask.exec_args, ['example.crw'])
        self.assertEqual(subtask.output_file_paths, ['example.ppm'])

    def test_verification(self):
        self.assertFalse(
            self.benchmark.verify_result(['no', 'expected', 'output', 'file'])
        )

        with patch('builtins.open', mock_open(read_data='actual_content')) as m:
            # Mock opening two separate files with different contents.
            m.side_effect = (
                m.return_value,
                mock_open(read_data='ref_content').return_value,
            )
            self.assertFalse(
                self.benchmark.verify_result(['/path/to/example.ppm'])
            )

        with patch('builtins.open', mock_open(read_data='ref_content')) as m:
            # Mock opening two separate files with equal contents.
            m.side_effect = (
                m.return_value,
                mock_open(read_data='ref_content').return_value,
            )
            self.assertTrue(
                self.benchmark.verify_result(['/path/to/example.ppm'])
            )
