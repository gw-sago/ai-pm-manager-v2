module.exports = {
  entry: './src/main.ts',
  module: {
    rules: require('./webpack.rules'),
  },
  resolve: {
    extensions: ['.js', '.ts', '.jsx', '.tsx', '.css', '.json'],
  },
  externals: {
    'better-sqlite3': 'commonjs better-sqlite3',
  },
};
