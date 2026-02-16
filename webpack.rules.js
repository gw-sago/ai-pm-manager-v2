module.exports = [
  {
    test: /\.node$/,
    use: 'node-loader',
  },
  {
    test: /\.(ts|tsx)$/,
    exclude: /(node_modules|\.webpack)/,
    use: {
      loader: 'ts-loader',
      options: {
        transpileOnly: true,
      },
    },
  },
];
