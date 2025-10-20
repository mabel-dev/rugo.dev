#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

// Platform detection for SIMD support
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
    #define HAVE_SSE2 1
    #ifdef __SSE4_2__
        #define HAVE_SSE42 1
    #endif
    #ifdef __AVX2__
        #define HAVE_AVX2 1
    #endif
#endif

#ifdef HAVE_SSE2
#include <emmintrin.h>  // SSE2
#endif

#ifdef HAVE_SSE42
#include <nmmintrin.h>  // SSE4.2
#endif

#ifdef HAVE_AVX2
#include <immintrin.h>  // AVX2
#endif

namespace simd {

// Fast newline search using SIMD when available
inline const char* FindNewline(const char* data, size_t size) {
    const char* ptr = data;
    const char* end = data + size;

#ifdef HAVE_AVX2
    // AVX2: Process 32 bytes at a time
    if (size >= 32) {
        __m256i newline_vec = _mm256_set1_epi8('\n');
        const char* avx_end = end - 31;
        
        while (ptr < avx_end) {
            __m256i chunk = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(ptr));
            __m256i cmp = _mm256_cmpeq_epi8(chunk, newline_vec);
            int mask = _mm256_movemask_epi8(cmp);
            
            if (mask != 0) {
                // Found a newline - determine exact position
                int offset = __builtin_ctz(mask);
                return ptr + offset;
            }
            ptr += 32;
        }
    }
#elif defined(HAVE_SSE2)
    // SSE2: Process 16 bytes at a time
    if (size >= 16) {
        __m128i newline_vec = _mm_set1_epi8('\n');
        const char* sse_end = end - 15;
        
        while (ptr < sse_end) {
            __m128i chunk = _mm_loadu_si128(reinterpret_cast<const __m128i*>(ptr));
            __m128i cmp = _mm_cmpeq_epi8(chunk, newline_vec);
            int mask = _mm_movemask_epi8(cmp);
            
            if (mask != 0) {
                // Found a newline - determine exact position
                int offset = __builtin_ctz(mask);
                return ptr + offset;
            }
            ptr += 16;
        }
    }
#endif

    // Scalar fallback for remaining bytes
    while (ptr < end) {
        if (*ptr == '\n') {
            return ptr;
        }
        ptr++;
    }
    
    return nullptr;
}

// Fast whitespace skipping using SIMD
inline const char* SkipWhitespace(const char* data, size_t size) {
    const char* ptr = data;
    const char* end = data + size;

#ifdef HAVE_AVX2
    // AVX2: Process 32 bytes at a time
    if (size >= 32) {
        __m256i space_vec = _mm256_set1_epi8(' ');
        __m256i tab_vec = _mm256_set1_epi8('\t');
        __m256i cr_vec = _mm256_set1_epi8('\r');
        const char* avx_end = end - 31;
        
        while (ptr < avx_end) {
            __m256i chunk = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(ptr));
            
            // Check which bytes are whitespace
            __m256i is_space = _mm256_cmpeq_epi8(chunk, space_vec);
            __m256i is_tab = _mm256_cmpeq_epi8(chunk, tab_vec);
            __m256i is_cr = _mm256_cmpeq_epi8(chunk, cr_vec);
            
            // Combine all whitespace checks
            __m256i is_ws = _mm256_or_si256(_mm256_or_si256(is_space, is_tab), is_cr);
            int mask = _mm256_movemask_epi8(is_ws);
            
            if (mask != 0xFFFFFFFF) {
                // Found a non-whitespace character
                int offset = __builtin_ctz(~mask);
                return ptr + offset;
            }
            ptr += 32;
        }
    }
#elif defined(HAVE_SSE2)
    // SSE2: Process 16 bytes at a time
    if (size >= 16) {
        __m128i space_vec = _mm_set1_epi8(' ');
        __m128i tab_vec = _mm_set1_epi8('\t');
        __m128i cr_vec = _mm_set1_epi8('\r');
        const char* sse_end = end - 15;
        
        while (ptr < sse_end) {
            __m128i chunk = _mm_loadu_si128(reinterpret_cast<const __m128i*>(ptr));
            
            // Check which bytes are whitespace
            __m128i is_space = _mm_cmpeq_epi8(chunk, space_vec);
            __m128i is_tab = _mm_cmpeq_epi8(chunk, tab_vec);
            __m128i is_cr = _mm_cmpeq_epi8(chunk, cr_vec);
            
            // Combine all whitespace checks
            __m128i is_ws = _mm_or_si128(_mm_or_si128(is_space, is_tab), is_cr);
            int mask = _mm_movemask_epi8(is_ws);
            
            if (mask != 0xFFFF) {
                // Found a non-whitespace character
                int offset = __builtin_ctz(~mask & 0xFFFF);
                return ptr + offset;
            }
            ptr += 16;
        }
    }
#endif

    // Scalar fallback for remaining bytes
    while (ptr < end && (*ptr == ' ' || *ptr == '\t' || *ptr == '\r')) {
        ptr++;
    }
    
    return ptr;
}

// Fast quote detection for string parsing
inline const char* FindQuote(const char* data, size_t size) {
    const char* ptr = data;
    const char* end = data + size;

#ifdef HAVE_AVX2
    // AVX2: Process 32 bytes at a time
    if (size >= 32) {
        __m256i quote_vec = _mm256_set1_epi8('"');
        __m256i backslash_vec = _mm256_set1_epi8('\\');
        const char* avx_end = end - 31;
        bool escaped = false;
        
        while (ptr < avx_end) {
            __m256i chunk = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(ptr));
            __m256i is_quote = _mm256_cmpeq_epi8(chunk, quote_vec);
            __m256i is_backslash = _mm256_cmpeq_epi8(chunk, backslash_vec);
            
            int quote_mask = _mm256_movemask_epi8(is_quote);
            int backslash_mask = _mm256_movemask_epi8(is_backslash);
            
            if (quote_mask != 0 || backslash_mask != 0) {
                // Found a quote or backslash, need to handle escapes carefully
                // Fall back to scalar processing for this chunk
                for (int i = 0; i < 32 && ptr < end; i++, ptr++) {
                    if (escaped) {
                        escaped = false;
                    } else if (*ptr == '\\') {
                        escaped = true;
                    } else if (*ptr == '"') {
                        return ptr;
                    }
                }
                continue;
            }
            ptr += 32;
        }
    }
#elif defined(HAVE_SSE2)
    // SSE2: Process 16 bytes at a time
    if (size >= 16) {
        __m128i quote_vec = _mm_set1_epi8('"');
        __m128i backslash_vec = _mm_set1_epi8('\\');
        const char* sse_end = end - 15;
        bool escaped = false;
        
        while (ptr < sse_end) {
            __m128i chunk = _mm_loadu_si128(reinterpret_cast<const __m128i*>(ptr));
            __m128i is_quote = _mm_cmpeq_epi8(chunk, quote_vec);
            __m128i is_backslash = _mm_cmpeq_epi8(chunk, backslash_vec);
            
            int quote_mask = _mm_movemask_epi8(is_quote);
            int backslash_mask = _mm_movemask_epi8(is_backslash);
            
            if (quote_mask != 0 || backslash_mask != 0) {
                // Found a quote or backslash, need to handle escapes carefully
                // Fall back to scalar processing for this chunk
                for (int i = 0; i < 16 && ptr < end; i++, ptr++) {
                    if (escaped) {
                        escaped = false;
                    } else if (*ptr == '\\') {
                        escaped = true;
                    } else if (*ptr == '"') {
                        return ptr;
                    }
                }
                continue;
            }
            ptr += 16;
        }
    }
#endif

    // Scalar fallback for remaining bytes
    bool escaped = false;
    while (ptr < end) {
        if (escaped) {
            escaped = false;
        } else if (*ptr == '\\') {
            escaped = true;
        } else if (*ptr == '"') {
            return ptr;
        }
        ptr++;
    }
    
    return nullptr;
}

// Fast character search (for delimiters like ':', ',', '}', etc.)
inline const char* FindChar(const char* data, size_t size, char target) {
    const char* ptr = data;
    const char* end = data + size;

#ifdef HAVE_AVX2
    // AVX2: Process 32 bytes at a time
    if (size >= 32) {
        __m256i target_vec = _mm256_set1_epi8(target);
        const char* avx_end = end - 31;
        
        while (ptr < avx_end) {
            __m256i chunk = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(ptr));
            __m256i cmp = _mm256_cmpeq_epi8(chunk, target_vec);
            int mask = _mm256_movemask_epi8(cmp);
            
            if (mask != 0) {
                int offset = __builtin_ctz(mask);
                return ptr + offset;
            }
            ptr += 32;
        }
    }
#elif defined(HAVE_SSE2)
    // SSE2: Process 16 bytes at a time
    if (size >= 16) {
        __m128i target_vec = _mm_set1_epi8(target);
        const char* sse_end = end - 15;
        
        while (ptr < sse_end) {
            __m128i chunk = _mm_loadu_si128(reinterpret_cast<const __m128i*>(ptr));
            __m128i cmp = _mm_cmpeq_epi8(chunk, target_vec);
            int mask = _mm_movemask_epi8(cmp);
            
            if (mask != 0) {
                int offset = __builtin_ctz(mask);
                return ptr + offset;
            }
            ptr += 16;
        }
    }
#endif

    // Scalar fallback for remaining bytes
    while (ptr < end) {
        if (*ptr == target) {
            return ptr;
        }
        ptr++;
    }
    
    return nullptr;
}

} // namespace simd
