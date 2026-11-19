// Only the disposable recovery drill executes this helper, under a hard cgroup
// memory/swap limit. Touch a fixed upper bound; never stress host memory directly.
package main

import "runtime"

func main() {
	memory := make([]byte, 512<<20)
	for i := 0; i < len(memory); i += 4096 {
		memory[i] = 1
	}
	runtime.KeepAlive(memory)
	// Reaching this point means the cgroup did not enforce the expected limit.
	panic("expected memory limit was not enforced")
}
