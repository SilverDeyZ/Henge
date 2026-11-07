/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HENGEVM_RAM_DIAG_H
#define HENGEVM_RAM_DIAG_H

#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_error.h>
#include <mach/task_info.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Allocation diagnostics only: no probing, page touching or mapping changes.
   Keep errno intact even if task_info, error decoding or stderr changes it. */
typedef struct {
    const char *strategy, *operation;
    uint64_t bytes, offset;
    int flags, protection;
} HvRamTrace;

static inline void hv_ram_trace_emit(const HvRamTrace *t, const char *phase, const void *address,
                                     const char *domain, int result, int error) {
    int saved_errno = errno;
    task_vm_info_data_t info = {0};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    kern_return_t kr = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count);
    char usage[512];
    if (kr != KERN_SUCCESS || count < TASK_VM_INFO_REV1_COUNT) {
        snprintf(usage, sizeof usage, "memory=unavailable task_info_kr=%d (%s) count=%u",
                 kr, mach_error_string(kr), (unsigned)count);
    } else {
        snprintf(usage, sizeof usage,
                 "footprint_bytes=%llu resident_bytes=%llu virtual_bytes=%llu regions=%d page_bytes=%d",
                 (unsigned long long)info.phys_footprint, (unsigned long long)info.resident_size,
                 (unsigned long long)info.virtual_size, info.region_count, info.page_size);
        if (count >= TASK_VM_INFO_REV2_COUNT) {
            size_t used = strlen(usage);
            snprintf(usage + used, sizeof usage - used, " min_address=0x%llx max_address=0x%llx",
                     (unsigned long long)info.min_address, (unsigned long long)info.max_address);
        }
        if (count >= TASK_VM_INFO_REV4_COUNT) {
            size_t used = strlen(usage);
            snprintf(usage + used, sizeof usage - used, " limit_bytes_remaining=%llu",
                     (unsigned long long)info.limit_bytes_remaining);
        }
    }
    const char *detail = !domain || !error ? "none" :
                         !strcmp(domain, "mach") ? mach_error_string(error) : strerror(error);
    const char *status = !domain ? "pending" :
                         (!strcmp(domain, "errno") ? result >= 0 : result == 0) ? "ok" : "failed";
    fprintf(stderr, "hengevm: ram[%s] op=%s phase=%s bytes=%llu offset=%llu flags=0x%x prot=0x%x "
                    "address=%p status=%s domain=%s rc=%d error=%d (%s) %s\n",
            t->strategy, t->operation, phase, (unsigned long long)t->bytes, (unsigned long long)t->offset,
            (unsigned)t->flags, (unsigned)t->protection, address,
            status, domain ? domain : "none",
            result, error, detail, usage);
    errno = saved_errno;
}

static inline HvRamTrace hv_ram_trace_begin(const char *strategy, const char *operation,
                                            uint64_t bytes, uint64_t offset, int flags,
                                            int protection, const void *address) {
    HvRamTrace t = {strategy, operation, bytes, offset, flags, protection};
    hv_ram_trace_emit(&t, "before", address, NULL, 0, 0);
    return t;
}

static inline void hv_ram_trace_mach(const HvRamTrace *t, kern_return_t kr, const void *address) {
    hv_ram_trace_emit(t, "after", address, "mach", kr, kr);
}

/* Pass the syscall's result and errno captured immediately on failure.
   A successful syscall need not clear errno, so never decode it on success. */
static inline void hv_ram_trace_posix(const HvRamTrace *t, int result, int error, const void *address) {
    hv_ram_trace_emit(t, "after", address, "errno", result, result < 0 ? error : 0);
}

#endif
