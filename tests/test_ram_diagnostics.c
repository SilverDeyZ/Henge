/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exercise error reporting even when the memory snapshot itself fails or
   clobbers errno. On Darwin use the real SDK types; on Windows use the small
   test-only declarations in ram_diag_stubs (no kernel/mapping claims). */
#include <assert.h>
#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_error.h>
#include <mach/task_info.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static char output[4096];
static kern_return_t snapshot_result;
static mach_msg_type_number_t snapshot_count = TASK_VM_INFO_COUNT;

static kern_return_t fake_task_info(task_t task, int flavor, task_info_t data, mach_msg_type_number_t *count) {
    (void)task;
    assert(flavor == TASK_VM_INFO);
    task_vm_info_data_t *info = (task_vm_info_data_t *)data;
    *info = (task_vm_info_data_t){0};
    info->phys_footprint = 1048576;
    info->resident_size = 2097152;
    info->virtual_size = 8589934592ULL;
    info->region_count = 123;
    info->page_size = 16384;
    info->min_address = 0x100000000ULL;
    info->max_address = 0x400000000ULL;
    info->limit_bytes_remaining = 3145728;
    *count = snapshot_count;
    errno = EIO;
    return snapshot_result;
}

static const char *fake_mach_error_string(kern_return_t kr) {
    errno = EINVAL;
    return kr ? "injected Mach failure" : "success";
}

static int capture_fprintf(FILE *stream, const char *format, ...) {
    assert(stream == stderr);
    va_list args;
    va_start(args, format);
    int n = vsnprintf(output, sizeof output, format, args);
    va_end(args);
    assert(n >= 0 && (size_t)n < sizeof output);
    errno = EBADF;
    return n;
}

#define task_info fake_task_info
#define mach_error_string fake_mach_error_string
#define fprintf capture_fprintf
#include "../host/ram_diag.h"
#undef fprintf

#ifdef _WIN32
task_t mach_task_self(void) { return 1; }
#endif

int main(void) {
    errno = ENOENT;
    HvRamTrace trace = hv_ram_trace_begin("file", "open", 6ULL << 30, 128ULL << 20, 0x42, 3, NULL);
    assert(errno == ENOENT);
    assert(strstr(output, "phase=before"));
    assert(strstr(output, "status=pending"));
    assert(strstr(output, "bytes=6442450944 offset=134217728"));
    assert(strstr(output, "footprint_bytes=1048576 resident_bytes=2097152 virtual_bytes=8589934592"));
    assert(strstr(output, "max_address=0x400000000"));
    assert(strstr(output, "limit_bytes_remaining=3145728"));

    /* open succeeds with a positive fd, and stale errno is not a failure. */
    hv_ram_trace_posix(&trace, 7, ENOENT, NULL);
    assert(errno == ENOENT);
    assert(strstr(output, "status=ok domain=errno rc=7 error=0 (none)"));

    /* Model an ENOMEM from mmap, followed by cleanup changing errno. */
    int allocation_error = ENOMEM;
    errno = EBADF;
    hv_ram_trace_posix(&trace, -1, allocation_error, NULL);
    assert(errno == EBADF);
    char expected[80];
    snprintf(expected, sizeof expected, "status=failed domain=errno rc=-1 error=%d", ENOMEM);
    assert(strstr(output, expected));
    assert(strstr(output, strerror(ENOMEM)));

    errno = ENOENT;
    hv_ram_trace_mach(&trace, 8, NULL);
    assert(errno == ENOENT);
    assert(strstr(output, "status=failed domain=mach rc=8 error=8 (injected Mach failure)"));
    hv_ram_trace_mach(&trace, KERN_SUCCESS, NULL);
    assert(strstr(output, "status=ok domain=mach rc=0 error=0 (none)"));

    snapshot_result = 5;
    hv_ram_trace_posix(&trace, -1, allocation_error, NULL);
    assert(errno == ENOENT);
    assert(strstr(output, "memory=unavailable task_info_kr=5"));
    assert(strstr(output, expected));
    assert(!strstr(output, "footprint_bytes="));

    snapshot_result = KERN_SUCCESS;
    snapshot_count = TASK_VM_INFO_REV1_COUNT - 1;
    hv_ram_trace_mach(&trace, KERN_SUCCESS, NULL);
    assert(strstr(output, "memory=unavailable"));
    assert(!strstr(output, "footprint_bytes="));
    snapshot_count = TASK_VM_INFO_REV1_COUNT;
    hv_ram_trace_mach(&trace, KERN_SUCCESS, NULL);
    assert(strstr(output, "footprint_bytes="));
    assert(!strstr(output, "max_address="));
    assert(!strstr(output, "limit_bytes_remaining="));
    snapshot_count = TASK_VM_INFO_REV2_COUNT;
    hv_ram_trace_mach(&trace, KERN_SUCCESS, NULL);
    assert(strstr(output, "max_address="));
    assert(!strstr(output, "limit_bytes_remaining="));
    puts("RAM diagnostic tests passed");
    return 0;
}
