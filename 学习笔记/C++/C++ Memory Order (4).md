std::atomic_thread_fence 

## Fence-atomic synchronization

## Atomic-fence synchronization

## Fence-fence synchronization



```cpp
//Global
std::string computation(int);
void print( std::string );
 
std::atomic<int> arr[3] = { -1, -1, -1 };
std::string data[1000]; //non-atomic data
 
// Thread A, compute 3 values
void ThreadA( int v0, int v1, int v2 )
{
//assert( 0 <= v0, v1, v2 < 1000 );
data[v0] = computation(v0);
data[v1] = computation(v1);
data[v2] = computation(v2);
std::atomic_thread_fence(std::memory_order_release);
std::atomic_store_explicit(&arr[0], v0, std::memory_order_relaxed);
std::atomic_store_explicit(&arr[1], v1, std::memory_order_relaxed);
std::atomic_store_explicit(&arr[2], v2, std::memory_order_relaxed);
}
 
// Thread B, prints between 0 and 3 values already computed.
void ThreadB()
{
int v0 = std::atomic_load_explicit(&arr[0], std::memory_order_relaxed);
int v1 = std::atomic_load_explicit(&arr[1], std::memory_order_relaxed);
int v2 = std::atomic_load_explicit(&arr[2], std::memory_order_relaxed);
std::atomic_thread_fence(std::memory_order_acquire);
// v0, v1, v2 might turn out to be -1, some or all of them.
// otherwise it is safe to read the non-atomic data because of the fences:
if( v0 != -1 ) { print( data[v0] ); }
if( v1 != -1 ) { print( data[v1] ); }
if( v2 != -1 ) { print( data[v2] ); }
}
```



```cpp
const int num_mailboxes = 32;
std::atomic<int> mailbox_receiver[num_mailboxes];
std::string mailbox_data[num_mailboxes];
 
// The writer threads update non-atomic shared data 
// and then update mailbox_receiver[i] as follows
mailbox_data[i] = ...;
std::atomic_store_explicit(&mailbox_receiver[i], receiver_id, std::memory_order_release);
 
// Reader thread needs to check all mailbox[i], but only needs to sync with one
for (int i = 0; i < num_mailboxes; ++i) {
    if (std::atomic_load_explicit(&mailbox_receiver[i], std::memory_order_relaxed) == my_id) {
        std::atomic_thread_fence(std::memory_order_acquire); // synchronize with just one writer
        do_work( mailbox_data[i] ); // guaranteed to observe everything done in the writer thread before
                    // the atomic_store_explicit()
    }
 }
```



# Links

1. [https://en.cppreference.com/w/cpp/atomic/atomic_thread_fence](https://en.cppreference.com/w/cpp/atomic/atomic_thread_fence)
2. [https://blog.csdn.net/wxj1992/article/details/103917093](https://blog.csdn.net/wxj1992/article/details/103917093)