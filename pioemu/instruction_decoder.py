# Copyright 2021 Nathan Young
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from functools import partial, wraps
from .conditions import (
    always,
    gpio_low,
    gpio_high,
    transmit_fifo_not_empty,
    x_register_equals_zero,
    x_register_not_equal_to_y_register,
    x_register_not_equal_to_zero,
    y_register_equals_zero,
    y_register_not_equal_to_zero,
)
from .instruction import Instruction
from .instructions import (
    out_null,
    out_pindirs,
    out_pins,
    out_x,
    out_y,
    pull_blocking,
    pull_nonblocking,
)
from .primitive_operations import (
    read_from_isr,
    read_from_osr,
    read_from_pins,
    read_from_x,
    read_from_y,
    supplies_value,
    write_to_isr,
    write_to_osr,
    write_to_pin_directions,
    write_to_pins,
    write_to_program_counter,
    write_to_x,
    write_to_y,
)


class InstructionDecoder:
    """
    Decodes opcodes representing instructions into callables that emulate those
    instructions.
    """

    def __init__(self, shifter_for_osr):
        """
        Parameters:
        shifter_for_osr (Callable[[ShiftRegister, int], (ShiftRegister, int)]): Used for shifting the contents of the OSR.
        """

        self.decoding_functions = [
            self._decode_jmp,
            self._decode_wait,
            lambda _: None,
            self._decode_out,
            self._decode_pull,
            self._decode_mov,
            lambda _: None,
            self._decode_set,
        ]

        self.jmp_conditions = [
            always,
            x_register_equals_zero,
            x_register_not_equal_to_zero,
            y_register_equals_zero,
            y_register_not_equal_to_zero,
            x_register_not_equal_to_y_register,
            None,
            None,
        ]

        self.mov_sources = [
            read_from_pins,
            read_from_x,
            read_from_y,
            supplies_value(0),
            None,
            None,
            read_from_isr,
            read_from_osr,
        ]

        self.mov_destinations = [
            write_to_pins,
            write_to_x,
            write_to_y,
            None,
            None,
            None,
            write_to_isr,
            write_to_osr,
        ]

        self.out_destinations = [
            partial(out_pins, shifter_for_osr),
            partial(out_x, shifter_for_osr),
            partial(out_y, shifter_for_osr),
            partial(out_null, shifter_for_osr),
            partial(out_pindirs, shifter_for_osr),
            None,
            None,
            None,
        ]

        self.set_destinations = [
            write_to_pins,
            write_to_x,
            write_to_y,
            None,
            write_to_pin_directions,
            None,
            None,
            None,
            None,
        ]

    def decode(self, opcode):
        """
        Decodes the given opcode and returns a callable which emulates it.

        Parameters:
        opcode (int): The opcode to decode.

        Returns:
        Instruction: Representation of the instruction or None.
        """

        decoding_function = self.decoding_functions[(opcode >> 13) & 7]
        return decoding_function(opcode)

    def _decode_jmp(self, opcode):
        address = opcode & 0x1F
        condition = self.jmp_conditions[(opcode >> 5) & 7]

        if condition is not None:
            return Instruction(
                condition,
                partial(write_to_program_counter, supplies_value(address)),
            )
        else:
            return None

    def _decode_mov(self, opcode):
        read_from_source = self.mov_sources[opcode & 7]

        return self._make_instruction_from_lookup_table(
            opcode, self.mov_destinations, read_from_source
        )

    def _decode_out(self, opcode):
        bit_count = opcode & 0x1F

        if bit_count == 0:
            bit_count = 32

        return self._make_instruction_from_lookup_table(
            opcode, self.out_destinations, bit_count
        )

    def _decode_set(self, opcode):
        return self._make_instruction_from_lookup_table(
            opcode, self.set_destinations, supplies_value(opcode & 0x1F)
        )

    def _decode_pull(self, opcode):
        if opcode & 0x0020:
            return Instruction(transmit_fifo_not_empty, pull_blocking)
        else:
            return Instruction(always, pull_nonblocking)

    def _decode_wait(self, opcode):
        index = opcode & 0x001F

        if opcode & 0x0080:
            condition = partial(gpio_high, index)
        else:
            condition = partial(gpio_low, index)

        return Instruction(condition, lambda state: state)

    def _make_instruction_from_lookup_table(self, opcode, lookup_table, param):
        function = lookup_table[(opcode >> 5) & 7]

        if function is not None:
            return Instruction(always, partial(function, param))
        else:
            return None