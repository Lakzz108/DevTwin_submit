package main

import "fmt"

type Greeter struct{}

func (g Greeter) Greet() string { return fmt.Sprint("hello") }

func main() {}
