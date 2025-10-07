import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
describe('integration testing on i18n package', function () {
    afterAll(function () {
        fs.rmSync('./locales/tests', { recursive: true, force: true });
    });
    test('cmd extract-translation:impress', function () {
        // To be sure the file is not here
        fs.rmSync('./locales/impress/translations-crowdin.json', {
            recursive: true,
            force: true,
        });
        expect(fs.existsSync('./locales/impress/translations-crowdin.json')).toBeFalsy();
        // Generate the file
        execSync('yarn extract-translation:impress');
        expect(fs.existsSync('./locales/impress/translations-crowdin.json')).toBeTruthy();
    });
    test('cmd format-deploy', function () {
        // To be sure the tests folder is not here
        fs.rmSync('./locales/tests', { recursive: true, force: true });
        expect(fs.existsSync('./locales/tests')).toBeFalsy();
        // Generate english json file
        fs.mkdirSync('./locales/tests/en/', { recursive: true });
        fs.writeFileSync('./locales/tests/en/translations.json', JSON.stringify({ test: { message: 'My test' } }), 'utf8');
        expect(fs.existsSync('./locales/tests/en/translations.json')).toBeTruthy();
        fs.mkdirSync('./locales/tests/fr/', { recursive: true });
        fs.writeFileSync('./locales/tests/fr/translations.json', JSON.stringify({ test: { message: 'Mon test' } }), 'utf8');
        expect(fs.existsSync('./locales/tests/fr/translations.json')).toBeTruthy();
        // Execute format-deploy command
        var output = './locales/tests/translations.json';
        execSync("node ./format-deploy.mjs --app=tests --output=".concat(output));
        var json = JSON.parse(fs.readFileSync(output, 'utf8'));
        expect(json).toEqual({
            en: {
                translation: { test: 'My test' },
            },
            fr: {
                translation: { test: 'Mon test' },
            },
        });
    });
    test('cmd format-deploy throws an error when translation file is not found', function () {
        // To be sure the tests folder is not here
        fs.rmSync('./locales/tests', { recursive: true, force: true });
        expect(fs.existsSync('./locales/tests')).toBeFalsy();
        // Generate english json file
        fs.mkdirSync('./locales/tests/en/', { recursive: true });
        // Execute format-deploy command
        var output = './locales/tests/translations.json';
        var cmd = function () {
            execSync("node ./format-deploy.mjs --app=tests --output=".concat(output), {
                stdio: 'pipe',
            });
        };
        expect(cmd).toThrow("Error: File locales".concat(path.sep, "tests").concat(path.sep, "en").concat(path.sep, "translations.json not found!"));
    });
    test('cmd format-deploy throws an error when no translation to deploy', function () {
        // To be sure the tests folder is not here
        fs.rmSync('./locales/tests', { recursive: true, force: true });
        expect(fs.existsSync('./locales/tests')).toBeFalsy();
        // Generate english json file
        fs.mkdirSync('./locales/tests/', { recursive: true });
        // Execute format-deploy command
        var output = './locales/tests/translations.json';
        var cmd = function () {
            execSync("node ./format-deploy.mjs --app=tests --output=".concat(output), {
                stdio: 'pipe',
            });
        };
        expect(cmd).toThrow('Error: No translation to deploy');
    });
});
