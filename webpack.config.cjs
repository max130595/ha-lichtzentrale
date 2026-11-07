// Geändert für Lichtzentrale
const path = require('node:path');
const fs = require('node:fs');
const webpack = require('webpack');
const TerserPlugin = require('terser-webpack-plugin');
module.exports = {
  mode: 'production', entry: './js/index.ts',
  output: { filename: 'lichtzentrale_panel.js', path: path.resolve(__dirname, 'custom_components/lichtzentrale/frontend'), clean: true },
  resolve: { extensions: ['.ts', '.tsx', '.js'] },
  module: { rules: [{ test: /\.tsx?$/, loader: 'ts-loader', exclude: /node_modules/ }] },
  optimization: { moduleIds: 'deterministic', chunkIds: 'deterministic', minimizer: [new TerserPlugin({ extractComments: true })] },
  plugins: [new webpack.BannerPlugin({ banner: '// Geändert für Lichtzentrale', raw: true, stage: webpack.Compilation.PROCESS_ASSETS_STAGE_REPORT }), {apply(compiler) {
    compiler.hooks.thisCompilation.tap('DependencyLicenses', compilation => {
      compilation.hooks.processAssets.tap({name: 'DependencyLicenses', stage: webpack.Compilation.PROCESS_ASSETS_STAGE_ADDITIONAL}, () => {
        const licenses = ['react', 'react-dom', 'scheduler'].map(name => `${name}\n${fs.readFileSync(path.join(__dirname, 'node_modules', name, 'LICENSE'), 'utf8')}`).join('\n\n');
        compilation.emitAsset('THIRD_PARTY_LICENSES.txt', new webpack.sources.RawSource(licenses));
      });
    });
  }}],
  devtool: false,
};
