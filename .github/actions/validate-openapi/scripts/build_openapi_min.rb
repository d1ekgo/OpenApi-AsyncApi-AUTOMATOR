#!/usr/bin/env ruby
require "yaml"
require "json"

input_index = ARGV.index("--input")
output_index = ARGV.index("--output")

abort("Missing --input") unless input_index && ARGV[input_index + 1]
abort("Missing --output") unless output_index && ARGV[output_index + 1]

input_path = ARGV[input_index + 1]
output_path = ARGV[output_index + 1]

raw = File.read(input_path, encoding: "UTF-8")

data =
  begin
    parsed = YAML.safe_load(
      raw,
      permitted_classes: [],
      permitted_symbols: [],
      aliases: false
    )
    parsed.is_a?(Hash) ? parsed : {}
  rescue
    begin
      parsed = JSON.parse(raw)
      parsed.is_a?(Hash) ? parsed : {}
    rescue
      {}
    end
  end

top_level_keys = [
  "openapi",
  "info",
  "servers",
  "paths",
  "security",
  "tags",
  "externalDocs"
]

component_keys = [
  "schemas",
  "responses",
  "parameters",
  "requestBodies",
  "securitySchemes",
  "headers",
  "examples",
  "links",
  "callbacks"
]

min_spec = {}

top_level_keys.each do |key|
  min_spec[key] = data[key] if data.key?(key)
end

components = data["components"]
if components.is_a?(Hash)
  min_components = {}
  component_keys.each do |key|
    min_components[key] = components[key] if components.key?(key)
  end
  min_spec["components"] = min_components unless min_components.empty?
end

File.write(output_path, YAML.dump(min_spec))
