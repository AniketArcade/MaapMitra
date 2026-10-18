const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);
// Shared API types live outside mobile/ (type-only imports, erased at build time).
config.watchFolders = [path.resolve(__dirname, "../packages/api-types")];
module.exports = config;
