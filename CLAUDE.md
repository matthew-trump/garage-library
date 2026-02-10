# Book Alpha

An app that will help me convert by spreadsheet method of keeping track of my books.

Here we have a json file call garage-library.json

The structure of the json is

{
    "name" : "Garage library",
    "stacks" : {
        "A" : [
            {
                "title": "Title of book at top of stack A",
                "author": "Author(s) of the book at top of stack A",
                "publisher":"Dover"

            }, ...
        ],
        "B" : [...],
        ...
    }
}

where title is string, author can be null, and publisher is optional.
