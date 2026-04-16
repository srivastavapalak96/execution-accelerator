package com.example;

import org.apache.commons.text.StringSubstitutor;

import java.util.Map;

/**
 * Trivial entry point that exercises the vulnerable commons-text dependency.
 *
 * The exact behavior is unimportant; what matters is that the dependency
 * appears in {@code mvn dependency:tree} output so integration tests can
 * verify direct/transitive classification and post-mutation resolution.
 */
public final class App {

    private App() {}

    public static String greet(String name) {
        StringSubstitutor sub = new StringSubstitutor(Map.of("name", name));
        return sub.replace("Hello, ${name}!");
    }

    public static void main(String[] args) {
        System.out.println(greet(args.length > 0 ? args[0] : "world"));
    }
}
