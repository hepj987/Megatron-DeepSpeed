# coding=utf-8
# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import pathlib
import subprocess

from torch.utils import cpp_extension


def load(args):

    # Setting this param to a list has a problem of generating different
    # compilation commands (with diferent order of architectures) and
    # leading to recompilation of fused kernels. Set it to empty string
    # to avoid recompilation and assign arch flags explicity in
    # extra_cuda_cflags below
    #
    # but if a user wants to set an explicit list of archs to compile to, then let that list
    # through:
    arch_list = os.environ.get('TORCH_CUDA_ARCH_LIST', None)
    if arch_list is None:
        os.environ["TORCH_CUDA_ARCH_LIST"] = ""

    # # Check if cuda 11 is installed for compute capability 8.0
    # cc_flag = []
    # _, bare_metal_major, _ = _get_cuda_bare_metal_version(
    #     cpp_extension.CUDA_HOME)
    # if int(bare_metal_major) >= 11:
    #     cc_flag.append('-gencode')
    #     cc_flag.append('arch=compute_80,code=sm_80')

    # Build path
    srcpath = pathlib.Path(__file__).parent.absolute()
    buildpath = srcpath / 'build'
    buildpath.mkdir(parents=True, exist_ok=True)

    # Helper function to build the kernels.
    def _cpp_extention_load_helper(name, sources, extra_cuda_flags):
        return cpp_extension.load(
            name=name,
            sources=sources,
            build_directory=buildpath,
            extra_cflags=['-O3',],
            extra_cuda_cflags=['-O3'] + extra_cuda_flags,
            verbose=(args.rank == 0)
        )
                               # '-gencode', 'arch=compute_70,code=sm_70',

    # ==============
    # Fused softmax.
    # ==============

    if args.masked_softmax_fusion:
        extra_cuda_flags = ['-U__CUDA_NO_HALF_OPERATORS__',
                            '-U__CUDA_NO_HALF_CONVERSIONS__']
        
        # Upper triangular softmax.
        sources=[srcpath / 'scaled_upper_triang_masked_softmax.cpp',
                 srcpath / 'scaled_upper_triang_masked_softmax_cuda.cu']
        scaled_upper_triang_masked_softmax_cuda = _cpp_extention_load_helper(
            "scaled_upper_triang_masked_softmax_cuda",
            sources, extra_cuda_flags)

        # Masked softmax.
        sources=[srcpath / 'scaled_masked_softmax.cpp',
                 srcpath / 'scaled_masked_softmax_cuda.cu']
        scaled_masked_softmax_cuda = _cpp_extention_load_helper(
            "scaled_masked_softmax_cuda", sources, extra_cuda_flags)

    # =================================
    # Mixed precision fused layer norm.
    # =================================

    extra_cuda_flags = []
    sources=[srcpath / 'layer_norm_cuda.cpp',
             srcpath / 'layer_norm_cuda_kernel.cu']
    fused_mix_prec_layer_norm_cuda = _cpp_extention_load_helper(
        "fused_mix_prec_layer_norm_cuda", sources, extra_cuda_flags)


def _get_cuda_bare_metal_version(cuda_dir):
    raw_output = subprocess.check_output([cuda_dir + "/bin/hipcc", "--version"],
                                         universal_newlines=True)
    output = raw_output.split()
    release_idx = output.index("version") + 1
    release = output[release_idx].split(".")
    bare_metal_major = release[0]
    bare_metal_minor = release[1][0]

    return raw_output, bare_metal_major, bare_metal_minor


def _create_build_dir(buildpath):
    try:
        os.mkdir(buildpath)
    except OSError:
        if not os.path.isdir(buildpath):
            print(f"Creation of the build directory {buildpath} failed")
