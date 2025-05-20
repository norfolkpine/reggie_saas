import { execSync } from 'child_process';
import fs from 'fs';
describe('checks all the frontend translation are made', function () {
    it('checks missing translation. If this test fails, go to https://crowdin.com/', function () {
        // Extract the translations
        execSync('yarn extract-translation:impress -c ./i18next-parser.config.jest.mjs');
        var outputCrowdin = './locales/impress/translations-crowdin.json';
        var jsonCrowdin = JSON.parse(fs.readFileSync(outputCrowdin, 'utf8'));
        var listKeysCrowdin = Object.keys(jsonCrowdin).sort();
        // Check the translations in the app impress
        var outputimpress = '../../apps/impress/src/i18n/translations.json';
        var jsonimpress = JSON.parse(fs.readFileSync(outputimpress, 'utf8'));
        // Our keys are in english, so we don't need to check the english translation
        Object.keys(jsonimpress)
            .filter(function (key) { return key !== 'en'; })
            .forEach(function (key) {
            var listKeysimpress = Object.keys(jsonimpress[key].translation).sort();
            var missingKeys = listKeysCrowdin.filter(function (element) { return !listKeysimpress.includes(element); });
            var additionalKeys = listKeysimpress.filter(function (element) { return !listKeysCrowdin.includes(element); });
            if (missingKeys.length > 0) {
                console.log("Missing keys in impress translations that should be translated in Crowdin, got to https://crowdin.com/ :", missingKeys);
            }
            if (additionalKeys.length > 0) {
                console.log("Additional keys in impress translations that seems not present in this branch:", additionalKeys);
            }
            expect(missingKeys.length).toBe(0);
        });
    });
});
