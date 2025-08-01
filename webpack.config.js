const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const TerserPlugin = require('terser-webpack-plugin');

module.exports = {
  entry: {
    'site-base': './assets/site-base.js',  // base styles shared between frameworks
    'site-tailwind': './assets/site-tailwind.js',  // required for tailwindcss styles
    site: './assets/javascript/site.js',  // global site javascript
    app: './assets/javascript/app.js',  // logged-in javascript
    dashboard: './assets/javascript/shadcn-dashboard/index.jsx',
    teams: './assets/javascript/teams/teams.jsx',
    'edit-team': './assets/javascript/teams/edit-team.jsx',
  },
  output: {
    path: path.resolve(__dirname, './static'),
    filename: 'js/[name]-bundle.js',
    library: ["SiteJS", "[name]"],
  },
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx'],
    alias: {
      '@/components': path.resolve(__dirname, './assets/javascript/shadcn/components'),
      '@/utilities': path.resolve(__dirname, './assets/javascript/utilities'),
      '@': path.resolve(__dirname, './assets/javascript'),
    },
    fallback: {
      'use-sync-external-store/shim': require.resolve('use-sync-external-store/shim')
    },
  },
  module: {
    rules: [
      {
        test: /\.(js|jsx|ts|tsx)$/,
        exclude: /node_modules/,
        use: {
          loader: "babel-loader",
          options: {
            presets: [
              '@babel/preset-env',
              "@babel/preset-react",
              '@babel/preset-typescript'
            ]
          }
        }
      },
      {
        test: /\.css$/i,
        use: [
          MiniCssExtractPlugin.loader,
          'css-loader',
          'postcss-loader'
        ],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({
      'filename': 'css/[name].css',
    }),
  ],
  optimization: {
    minimizer: [new TerserPlugin({
      extractComments: false,  // disable generation of license.txt files
    })],
  },
  devtool: process.env.NODE_ENV === 'production' ? false : "eval-cheap-source-map",
};
