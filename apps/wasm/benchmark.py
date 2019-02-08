import os
from tempfile import TemporaryDirectory
import uuid

from golem.core.common import get_golem_path

from apps.wasm.task import WasmTaskDefinition, WasmTaskOptions
from apps.core.benchmark.benchmarkrunner import CoreBenchmark


class WasmTaskBenchmark(CoreBenchmark):
    def __init__(self):
        self._normalization_constant = 1000
        self.test_data_dir = os.path.join(
            get_golem_path(), 'apps', 'wasm', 'test_data'
        )
        self.output_dir = TemporaryDirectory()

        opts = WasmTaskOptions()
        opts.input_dir = os.path.join(self.test_data_dir, 'input')
        opts.output_dir = self.output_dir.name
        opts.js_name = 'dcraw.js'
        opts.wasm_name = 'dcraw.wasm'
        opts.subtasks = {
            'test_subtask': WasmTaskOptions.SubtaskOptions(
                'test_subtask', ['example.crw'], ['example.ppm']
            )
        }

        self._task_definition = WasmTaskDefinition()
        self._task_definition.task_id = str(uuid.uuid4())
        self._task_definition.options = opts
        self._task_definition.subtasks_count = 1
        self._task_definition.add_to_resources()

    @property
    def normalization_constant(self):
        return self._normalization_constant

    @property
    def task_definition(self):
        return self._task_definition

    def verify_result(self, result):
        for result_file in result:
            if os.path.basename(result_file) == 'example.ppm':
                actual_output_path = result_file
                break
        else:
            return False

        reference_output_path = os.path.join(
            self.test_data_dir, 'output', 'example.ppm'
        )
        with open(actual_output_path, 'rb') as f_act,\
                open(reference_output_path, 'rb') as f_ref:
            return f_act.read() == f_ref.read()
