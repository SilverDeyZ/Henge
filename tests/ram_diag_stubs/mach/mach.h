/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Only for the host-independent diagnostic test; not a Darwin ABI substitute. */
#ifndef HENGE_TEST_MACH_H
#define HENGE_TEST_MACH_H
#include <stdint.h>
typedef int kern_return_t;
typedef int task_t;
typedef int *task_info_t;
typedef unsigned mach_msg_type_number_t;
typedef struct {
    uint64_t phys_footprint, resident_size, virtual_size;
    int region_count, page_size;
    uint64_t min_address, max_address, limit_bytes_remaining;
} task_vm_info_data_t;
#define KERN_SUCCESS 0
#define TASK_VM_INFO 22
#define TASK_VM_INFO_REV1_COUNT 1u
#define TASK_VM_INFO_REV2_COUNT 2u
#define TASK_VM_INFO_REV4_COUNT 4u
#define TASK_VM_INFO_COUNT 4u
task_t mach_task_self(void);
kern_return_t task_info(task_t, int, task_info_t, mach_msg_type_number_t *);
const char *mach_error_string(kern_return_t);
#endif
